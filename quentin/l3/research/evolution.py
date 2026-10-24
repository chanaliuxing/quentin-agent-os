# quentin/l3/research/evolution.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple, Callable

from quentin.blueprint.gap_tracker import BlueprintGapTracker
from quentin.blueprint.gaps import BlueprintGap
from quentin.l3.research.experiments import ResearchManager
from quentin.l3.research.budget import BudgetController
from quentin.l3.research.schemas import ResearchBudgetConfig
from quentin.self_improvement.manager import SelfImprovementManager
from quentin.self_improvement.schemas import ImprovementTask

logger = logging.getLogger(__name__)


@dataclass
class EvolutionScoreWeights:
    """
    可配置的评分权重：
    - blueprint: 蓝皮书优先级
    - success:   历史成功率
    - latency:   延迟惩罚（秒）
    - cost:      成本惩罚（token / 货币单位）
    """
    blueprint: float = 1.0
    success: float = 1.0
    latency: float = -0.2
    cost: float = -0.1


@dataclass
class TaskScore:
    task_id: str
    capability: str
    requirement_id: str
    score: float
    factors: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvolutionStrategyManager:
    """
    根据蓝皮书 / 实验数据 / 预算，给出“下一步要优化哪些任务”。

    评分大致结构：
      score = blueprint_score * experiment_factor * budget_factor
    """

    def __init__(
        self,
        *,
        blueprint_tracker: Optional[BlueprintGapTracker] = None,
        research_manager: Optional[ResearchManager] = None,
        budget_controller: Optional[BudgetController] = None,
        si_manager: Optional[SelfImprovementManager] = None,
        score_weights: Optional[EvolutionScoreWeights] = None,
        stats_provider: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ) -> None:
        self.blueprint_tracker = blueprint_tracker or BlueprintGapTracker()
        self.research_manager = research_manager or ResearchManager()
        self.budget_controller = budget_controller or BudgetController(ResearchBudgetConfig())
        self.si_manager = si_manager or SelfImprovementManager()
        self.score_weights = score_weights or EvolutionScoreWeights()
        self.stats_provider = stats_provider

    # ---------- 主入口 ----------

    def suggest_next_tasks(
        self,
        *,
        limit: int = 10,
        allowed_statuses: Optional[List[str]] = None,
    ) -> List[Tuple[ImprovementTask, TaskScore]]:
        """
        返回按优先级排序的 ImprovementTask 列表及其评分。
        """
        tasks = self.si_manager.list_tasks()
        gaps = self.blueprint_tracker.scan()

        gap_index: Dict[Tuple[str, str], BlueprintGap] = {}
        for g in gaps:
            cap_id = getattr(g, "capability_id", None) or getattr(g, "category", None) or getattr(g, "requirement_id", None)
            key = (cap_id, g.requirement_id)
            gap_index[key] = g

        scores: List[Tuple[ImprovementTask, TaskScore]] = []

        allowed_statuses_lower = (
            {s.lower() for s in allowed_statuses} if allowed_statuses else None
        )

        for t in tasks:
            status = getattr(t, "overall_status", "") or ""
            if allowed_statuses_lower and status.lower() not in allowed_statuses_lower:
                continue

            cap = getattr(t, "capability", "") or ""
            req = getattr(t, "requirement_id", "") or ""

            gap = gap_index.get((cap, req))
            stats = self._get_task_level_stats(cap, req)
            ts = self._score_task(t, gap, stats)
            scores.append((t, ts))

        scores.sort(key=lambda c: c[1].score, reverse=True)
        return scores[:limit]

    # ---------- 打分逻辑 ----------

    def _score_task(
        self,
        task: ImprovementTask,
        gap: Optional[BlueprintGap],
        stats: Dict[str, Any],
    ) -> TaskScore:
        cap = getattr(task, "capability", "") or ""
        req = getattr(task, "requirement_id", "") or ""

        # 1) blueprint_score：来自蓝皮书优先级 + status
        if gap:
            base_priority = float(
                getattr(gap, "priority", None)
                or (gap.meta or {}).get("priority", 1)
                or 1
            )
            status = (
                getattr(gap, "spec_status", None)
                or (gap.meta or {}).get("status")
                or (gap.severity if hasattr(gap, "severity") else "")
            ).lower()
            status_weight_map = {
                "missing": 1.0,
                "placeholder": 0.8,
                "partial": 0.5,
                "ready": 0.2,
            }
            status_weight = status_weight_map.get(status, 0.3)
            blueprint_score = base_priority * 10.0 * status_weight
        else:
            blueprint_score = 1.0

        # 2) experiment_factor：看历史实验表现
        total_runs = int(stats.get("total_runs", 0) or stats.get("runs", 0) or 0)
        success_rate = stats.get("success_rate", stats.get("mean_success"))
        if success_rate is None:
            success_rate = 0.5  # 默认中性
        else:
            success_rate = float(success_rate)

        latency_sec = stats.get("avg_latency_sec", stats.get("latency_sec"))
        if latency_sec is not None:
            latency_sec = float(latency_sec)

        avg_cost = stats.get("avg_cost", stats.get("cost"))
        if avg_cost is not None:
            avg_cost = float(avg_cost)

        # 成功率越高越加分；延迟/成本越高越减分
        experiment_factor = (
            self.score_weights.success * success_rate
            + (self.score_weights.latency * latency_sec if latency_sec is not None else 0.0)
            + (self.score_weights.cost * avg_cost if avg_cost is not None else 0.0)
        )
        experiment_factor = max(experiment_factor, -2.0)  # 避免极端数值，但允许明显拉开差距


        # 3) budget_factor：看预算是否允许
        allowed = True
        if hasattr(self.budget_controller, "can_spend"):
            try:
                allowed = self.budget_controller.can_spend(
                    capability=cap,
                    cost_type="patches", # Assuming 1 patch per task
                    amount=1,
                )
            except Exception:
                logger.exception("BudgetController.can_spend failed; treating as allowed")
                allowed = True

        budget_factor = 1.0 if allowed else 0.1  # 预算不够，强行降权

        # Combine all factors
        score = (self.score_weights.blueprint * blueprint_score) * (1 + experiment_factor) * budget_factor

        factors = {
            "blueprint_score": blueprint_score,
            "experiment_factor": experiment_factor,
            "budget_factor": budget_factor,
            "total_runs": total_runs,
            "success_rate": success_rate,
            "latency_sec": latency_sec,
            "avg_cost": avg_cost,
        }

        return TaskScore(
            task_id=task.task_id,
            capability=cap,
            requirement_id=req,
            score=score,
            factors=factors,
        )

    # ---------- stats helper ----------
    def _get_task_level_stats(self, capability: str, requirement_id: str) -> Dict[str, Any]:
        if self.stats_provider:
            try:
                return self.stats_provider(capability, requirement_id) or {}
            except Exception:
                logger.exception("stats_provider failed for %s/%s", capability, requirement_id)

        getter = None
        if hasattr(self.research_manager, "get_task_level_stats"):
            getter = getattr(self.research_manager, "get_task_level_stats")
        elif hasattr(self.research_manager, "get_task_stats"):
            getter = getattr(self.research_manager, "get_task_stats")

        if getter:
            try:
                return getter(capability, requirement_id) or {}
            except Exception:
                logger.exception("ResearchManager.get_task_level_stats failed")
        return {}
