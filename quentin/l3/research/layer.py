from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import logging
import time
import uuid

from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.self_programming.schema import PatchTarget
from quentin.blueprint.gaps import BlueprintGap, BlueprintGapTracker
from quentin.l3.research.experiments import (
    ExperimentOrchestrator,
    ExperimentRecord,
    ExperimentRunResult,
    ExperimentConfig,
)
from quentin.eval.harness import EvalHarness
from quentin.l3.research.evolution import EvolutionStrategyManager # Make EvolutionStrategyManager visible

from quentin.l3.research.budget import BudgetController
from quentin.l3.research.schemas import ResearchCycleRequest, ResearchBudgetConfig, ResearchCycleResult

from quentin.l3.research.policy import PolicyAndGovernance
from quentin.l3.research.release_protocol import (
    FileBackedVariantLifecycleStore,
    shadow_request as _shadow_request,
    canary_request as _canary_request,
)


class ResearchLayer:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        experiment_orchestrator: ExperimentOrchestrator,
        budget_config: Optional[ResearchBudgetConfig] = None,
        eval_harness: Optional[EvalHarness] = None,
        policy: Optional[PolicyAndGovernance] = None,
        evolution_strategy_manager: Optional[EvolutionStrategyManager] = None,
        self_programming_engine: Optional[SelfProgrammingEngine] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.experiment_orchestrator = experiment_orchestrator
        self.eval_harness = eval_harness or experiment_orchestrator.eval_harness
        self.self_programming_engine = self_programming_engine
        self.lifecycle_store = FileBackedVariantLifecycleStore(repo_root=self.repo_root)
        
        self.budget_config = budget_config or ResearchBudgetConfig()
        self.budget_controller = BudgetController(self.budget_config)
        self.policy = policy or PolicyAndGovernance()
        self.evolution_strategy_manager = evolution_strategy_manager or EvolutionStrategyManager()

    def attach_self_programming_engine(self, engine: SelfProgrammingEngine) -> None:
        self.self_programming_engine = engine

    # --------------------------------------------------
    # P0.3: shadow/canary placeholders (schema-stable)
    # --------------------------------------------------

    def shadow_request(
        self,
        *,
        variant_id: str,
        environment: str = "sandbox",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run a candidate variant in "shadow" mode without impacting the primary output.
        v1 is a placeholder: it only records lifecycle + metadata.
        """
        req_id = f"shadow::{uuid.uuid4().hex}"
        return _shadow_request(
            store=self.lifecycle_store,
            variant_id=variant_id,
            environment=environment,
            request_id=req_id,
            meta=meta,
        )

    def canary_request(
        self,
        *,
        variant_id: str,
        fraction: float,
        environment: str = "sandbox",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Route a fraction of traffic to the candidate variant.
        v1 is a placeholder: it only records lifecycle + metadata.
        """
        req_id = f"canary::{uuid.uuid4().hex}"
        return _canary_request(
            store=self.lifecycle_store,
            variant_id=variant_id,
            environment=environment,
            request_id=req_id,
            fraction=fraction,
            meta=meta,
        )

    # --------------------------------------------------
    # 核心：蓝皮书自我改进循环
    # --------------------------------------------------
    def run_blueprint_improvement_cycle(
        self,
        *,
        runtime: Any,              # RuntimeFacade（带 council）
        max_gaps: int = 5,
        research_request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        v3 蓝皮书里的“Research & Evolution Layer”的一个最小实现：

          1. 用 BlueprintGapTracker 扫描 gap
          2. 对每个 gap 交给多 AI 议会（council）分析，生成 modules_to_improve
          3. 调用 SelfProgrammingEngine 为这些模块生成 patch proposal + 实验
        """
        research_request = research_request or {}

        # 1) 扫描 gap
        gap_tracker = BlueprintGapTracker(repo_root=self.repo_root)
        gaps = gap_tracker.scan(max_gaps=max_gaps)

        if not gaps:
            return {
                "status": "no_gaps_found",
                "gaps": [],
                "modules_to_improve": [],
                "self_programming_summary": None,
            }

        # 2) 用 council 分析每个 gap，得到 PatchTarget 列表
        modules_to_improve: List[PatchTarget] = []

        for gap in gaps:
            suggestions = self._analyze_gap_with_council(runtime, gap)
            for s in suggestions:
                modules_to_improve.append(
                    PatchTarget(
                        kind=s.get("kind", "module"),
                        path=s["path"],
                        symbol=s.get("symbol"),
                        constraints=s.get("constraints", {}),
                    )
                )

        # 3) 自编程引擎：生成 patch proposal + 注册实验
        if not self.self_programming_engine:
            sp_summary = {
                "status": "no_self_programming_engine_attached",
                "num_targets": len(modules_to_improve),
                "num_proposals": 0,
                "experiment_ids": [],
            }
        else:
            sp_summary = self.self_programming_engine.run_cycle(
                modules_to_improve=modules_to_improve,
                context={
                    "problem_description": "Blueprint improvement cycle",
                    "metrics": research_request.get("metrics", {}),
                    "notes": {
                        "selected_gap_ids": [g.requirement_id for g in gaps],
                        "gaps": [g.to_dict() for g in gaps],
                    },
                },
            )

        return {
            "status": "ok",
            "gaps": [g.to_dict() for g in gaps],
            "modules_to_improve": [
                {
                    "kind": t.kind,
                    "path": t.path,
                    "symbol": t.symbol,
                    "constraints": t.constraints,
                }
                for t in modules_to_improve
            ],
            "self_programming_summary": sp_summary,
        }

    # --------------------------------------------------
    # 内部：用多 AI 议会分析 gap -> 生成 PatchTarget 建议
    # --------------------------------------------------
    def _analyze_gap_with_council(
        self,
        runtime: Any,      # RuntimeFacade
        gap: BlueprintGap,
    ) -> List[Dict[str, Any]]:
        """
        对每个 gap 调用一次“多 AI 开会”：
          - 优先使用 runtime.council（多模型议会）
          - 如果没有 council，就退化为单模型 main_llm

        返回统一的 modules_to_improve 列表：
          [
            {
              "kind": "module",
              "path": "mutable/xxx.py",
              "symbol": "SomeClass.method",
              "constraints": {...}
            },
            ...
          ]
        """
        council = getattr(runtime, "council", None)
        llm = council or runtime.model_router

        gap_payload = {
            "requirement_id": gap.requirement_id,
            "category": gap.category,
            "description": gap.description,
            "severity": gap.severity,
            "module_hint": gap.module_hint,
            "symbol_hint": gap.symbol_hint,
            "meta": gap.meta or {},
        }

        # 让议会用 JSON 形式给出建议
        prompt = (
            "你们是一个多智能体评审委员会（包含速度、安全、成本、领域专家等视角），"
            "任务是根据下面这条“蓝皮书实现 gap”给出下一步工程落地建议。\n\n"
            "【输入 gap】(JSON)：\n"
            f"{json.dumps(gap_payload, ensure_ascii=False, indent=2)}\n\n"
            "【要求输出】请只输出一个 JSON 对象，不要带任何说明文字，格式如下：\n"
            "{\n"
            '  "modules_to_improve": [\n'
            "    {\n"
            '      "kind": "module",\n'
            '      "path": "mutable/xxx.py",\n'
            '      "symbol": "Optional[具体函数或类名]",\n'
            '      "constraints": {"reason": "为什么要改这里", "notes": "..."}\n'
            "    },\n"
            "    ...\n"
            "  ]\n"
            "}\n\n"
            "如果暂时无法定位到具体模块，请返回 modules_to_improve: []。"
        )

        try:
            if hasattr(llm, "deliberate"):
                 raw = llm.deliberate(question=prompt).final_answer
            elif callable(llm):
                 raw = llm(prompt)
            else:
                 raw = ""
        except Exception as e:
            # 出错时回退到“基于 module_hint 的默认建议”
            return self._fallback_suggestions_for_gap(gap, f"LLM error: {e!r}")

        try:
            data = json.loads(str(raw))
        except Exception:
            # 如果议会没按 JSON 格式说话，就回退
            return self._fallback_suggestions_for_gap(gap, "Failed to parse council JSON")

        modules = data.get("modules_to_improve", [])
        normalized: List[Dict[str, Any]] = []
        for m in modules:
            if "path" not in m:
                continue
            normalized.append(
                {
                    "kind": m.get("kind", "module"),
                    "path": m["path"],
                    "symbol": m.get("symbol"),
                    "constraints": m.get("constraints", {}),
                }
            )
        if not normalized:
            normalized = self._fallback_suggestions_for_gap(gap, "empty_council_suggestion")

        return normalized

    def _fallback_suggestions_for_gap(
        self,
        gap: BlueprintGap,
        reason: str,
    ) -> List[Dict[str, Any]]:
        """
        council 失效/不给建议时，用一个非常保守的默认策略：
          - 如果有 module_hint，就把它作为 patch target
          - 否则返回空列表
        """
        if not gap.module_hint:
            return []

        # 把蓝皮书里的 module_hint 映射为 mutable 下的一个候选路径（你也可以更细化）
        path = gap.module_hint
        if not path.startswith("mutable/") and not path.startswith("quentin/"):
            # 允许 spec 里直接写相对路径，例如 'quentin/runtime/cognitive_loop.py'
            # 这里不强行改成 mutable，由你自行管理哪些文件可以 auto_updatable
            pass

        return [
            {
                "kind": "module",
                "path": path,
                "symbol": gap.symbol_hint,
                "constraints": {
                    "from": "fallback",
                    "reason": reason,
                },
            }
        ]
    
    # Compatibility methods for previous API (106.md)
    def create_experiment(self, *, name: str, description: str, variants: List[str], tasks: List[Any], meta: Dict[str, Any] = None, experiment_id: str = None) -> ExperimentRecord:
        return self.experiment_orchestrator.create_experiment(name=name, description=description, variants=variants, tasks=tasks, meta=meta, experiment_id=experiment_id)

    def run_research_cycle(self, request: Optional[ResearchCycleRequest] = None) -> ResearchCycleResult:
        req = request or ResearchCycleRequest()
        started_at = time.time()

        all_experiments_ids = self.experiment_orchestrator.list_all_experiment_ids()
        all_experiments_records = [self.experiment_orchestrator.get_experiment_record(eid) for eid in all_experiments_ids]

        # 1. Select experiments based on strategy and budget
        selected_experiments = self.evolution_strategy_manager.select_experiments_for_cycle(
            experiments=all_experiments_records,
            strategy=req.strategy
        )
        limited_experiments = self.budget_controller.limit_experiments_for_cycle(
            candidates=selected_experiments,
            request=req
        )
        
        executed_experiments_ids: List[str] = []
        run_results: Dict[str, Dict[str, Any]] = {}
        variant_rankings: Dict[str, Dict[str, Any]] = {}

        for experiment_record in limited_experiments:
            exp_id = experiment_record.config.experiment_id
            
            # 2. Check policy approval
            if not self.policy.approve_experiment(experiment_record):
                logger.info(f"Experiment {exp_id} not approved by policy, skipping.")
                continue

            # 3. Run the experiment
            logger.info(f"Running experiment: {exp_id}")
            try:
                run_res = self.experiment_orchestrator.run_experiment(exp_id)
                run_results[exp_id] = run_res.to_dict()
                executed_experiments_ids.append(exp_id)

                # 4. Compare variants
                try:
                    ranking = self.experiment_orchestrator.compare_variants(exp_id)
                    variant_rankings[exp_id] = ranking
                except Exception as e:
                    logger.warning(f"Failed to compare variants for experiment {exp_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to run experiment {exp_id}: {e}")

        finished_at = time.time()
        return ResearchCycleResult(
            started_at=started_at,
            finished_at=finished_at,
            executed_experiments=executed_experiments_ids,
            run_results=run_results,
            variant_rankings=variant_rankings
        )

    def list_experiments(self) -> List[str]:
        return self.experiment_orchestrator.list_all_experiment_ids()

    def get_experiment_record(self, experiment_id: str) -> ExperimentRecord:
        return self.experiment_orchestrator.get_experiment_record(experiment_id)
    
    def export_results(self, experiment_id: str) -> Dict[str, Any]:
        """
        蓝皮书 API：export_results(experiment_id)
        委托给 ExperimentOrchestrator。
        """
        return self.experiment_orchestrator.export_results(experiment_id)
    
    def run_self_programming_cycle(self, modules_to_improve: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        # Compatibility with 118.md
        if not self.self_programming_engine: return {}
        targets = [PatchTarget(kind=m["kind"], path=m["path"], symbol=m.get("symbol"), constraints=m.get("constraints", {})) for m in modules_to_improve]
        return self.self_programming_engine.run_cycle(modules_to_improve=targets, context=context)
