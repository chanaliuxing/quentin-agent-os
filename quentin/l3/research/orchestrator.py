# quentin/l3/research/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from datetime import datetime, UTC
import logging

from quentin.l3.research.experiments import (
    ExperimentStore,
    ExperimentConfig,
    VariantConfig,
    ExperimentResult,
    VariantResult,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class ExperimentRunner(Protocol):
    """
    某一类组件的实验执行器接口。

    比如：
    - PlannerRunner：对不同 planner 策略的 Variant 做评测
    - ModelRouterRunner：对不同路由策略做评测
    - SkillEvolutionRunner：对不同技能演化策略做评测

    run_variant 必须返回 VariantResult。
    """

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ...


@dataclass
class OrchestratorConfig:
    """
    Orchestrator 的配置占位。
    目前没啥字段，以后可以放：
    - 默认评测 metric 名称
    - 同时运行的最大实验数量等
    """
    default_score_metric: str = "score"


class ExperimentOrchestrator:
    """
    v1：轻量实验编排器。

    特点：
    - 不绑定具体领域：只知道有“组件组件(component)”和“变体(variant)”；
    - 具体怎么评测由 ExperimentRunner 决定；
    - 结果统一写入 ExperimentStore。
    """

    def __init__(
        self,
        *,
        repo_root: str | None = None,
        store: Optional[ExperimentStore] = None,
        config: Optional[OrchestratorConfig] = None,
    ) -> None:
        from pathlib import Path

        self.repo_root = Path(repo_root or ".").resolve()
        self.store = store or ExperimentStore(repo_root=self.repo_root)
        self.config = config or OrchestratorConfig()

        # 每个 target_component 对应一个 Runner
        self.runners: Dict[str, ExperimentRunner] = {}

    # -------- Runner 注册 -------- #
    def register_runner(self, component: str, runner: ExperimentRunner) -> None:
        """
        注册某个组件的 Runner。

        component 如：
        - "planner"
        - "model_router"
        - "skill_evolution"
        """
        self.runners[component] = runner

    # -------- Experiment 管理 -------- #
    def create_experiment(
        self,
        *,
        name: str,
        purpose: str,
        target_component: str,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        variants: Optional[List[VariantConfig]] = None,
    ) -> ExperimentConfig:
        cfg = self.store.create_experiment(
            name=name,
            purpose=purpose,
            target_component=target_component,
            created_by=created_by,
            metadata=metadata,
            variants=variants,
        )
        logger.info(
            "ExperimentOrchestrator: created experiment %s for component=%s",
            cfg.experiment_id,
            target_component,
        )
        return cfg

    def run_experiment(
        self,
        experiment_id: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        score_metric: Optional[str] = None,
    ) -> ExperimentResult:
        """
        顺序执行指定实验的所有 variants，并产生 ExperimentResult。

        - context 由具体 Runner 自行解释（可包含数据集路径、离线样本集等）
        """
        cfg = self.store.load_config(experiment_id)
        if cfg is None:
            raise ValueError(f"ExperimentOrchestrator: experiment {experiment_id} not found")

        runner = self.runners.get(cfg.target_component)
        if runner is None:
            raise RuntimeError(
                f"ExperimentOrchestrator: no runner registered for component={cfg.target_component}"
            )

        result = ExperimentResult(
            experiment_id=experiment_id,
            status="running",
            started_at=datetime.now(UTC).isoformat(),
            finished_at=None,
            variant_results=[],
            best_variant_id=None,
            best_metric_name=None,
            notes="",
        )
        self.store.save_result(result)  # 立刻写一遍“running”状态

        metric_name = score_metric or self.config.default_score_metric
        best_score = None
        best_variant_id = None

        for v in cfg.variants:
            try:
                vr = runner.run_variant(cfg, v, context=context)
            except Exception as e:
                logger.exception(
                    "ExperimentOrchestrator: runner failed for experiment %s variant %s",
                    experiment_id,
                    v.variant_id,
                )
                # 失败也要写入一个结果占位
                vr = VariantResult(
                    variant_id=v.variant_id,
                    metrics={},
                    extra={"error": str(e)},
                )

            result.variant_results.append(vr)

            # 比较 score
            score = vr.metrics.get(metric_name)
            if score is not None:
                if best_score is None or score > best_score:
                    best_score = score
                    best_variant_id = v.variant_id

            # 每个 variant 跑完都可以增量保存一次（方便中断恢复）
            self.store.save_result(result)

        result.status = "completed"
        result.finished_at = datetime.now(UTC).isoformat()
        result.best_variant_id = best_variant_id
        result.best_metric_name = metric_name

        if best_variant_id is None:
            result.notes = (
                "No variant produced a valid score metric; "
                "best_variant_id remains None. Check metrics or runner implementation."
            )

        self.store.save_result(result)
        logger.info(
            "ExperimentOrchestrator: experiment %s completed. best_variant=%s metric=%s score=%s",
            experiment_id,
            best_variant_id,
            metric_name,
            best_score,
        )
        return result

    def compare_variants(
        self,
        experiment_id: str,
        metric_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        简单比较实验中各变体在指定 metric 上的表现。
        返回结构：
        {
          "experiment_id": ...,
          "metric": ...,
          "best_variant_id": ...,
          "scores": { variant_id: score_or_None, ... }
        }
        """
        result = self.store.load_result(experiment_id)
        if result is None:
            return None

        m = metric_name or result.best_metric_name or self.config.default_score_metric
        scores: Dict[str, Optional[float]] = {}
        best_variant_id = None
        best_score = None

        for vr in result.variant_results:
            score = vr.metrics.get(m)
            scores[vr.variant_id] = score
            if score is not None:
                if best_score is None or score > best_score:
                    best_score = score
                    best_variant_id = vr.variant_id

        return {
            "experiment_id": experiment_id,
            "metric": m,
            "best_variant_id": best_variant_id,
            "scores": scores,
        }
