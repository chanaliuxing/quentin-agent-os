# quentin/l3/research/runners/planner_offline_runner.py
from __future__ import annotations

from typing import Any, Dict, Optional, Callable
import logging

from quentin.l3.research.orchestrator import ExperimentRunner
from quentin.l3.research.experiments import (
    ExperimentConfig,
    VariantConfig,
    VariantResult,
)
from quentin.eval.spec import EvalDatasetSpec, EvalTaskSpec
from quentin.eval.harness import EvalHarness

logger = logging.getLogger(__name__)

# planner_fn: (task, variant, context) -> dict with keys: success, score, notes, etc.
PlannerFn = Callable[[EvalTaskSpec, VariantConfig, Dict[str, Any]], Dict[str, Any]]


class PlannerOfflineRunner(ExperimentRunner):
    """
    针对 planner 组件的离线评测 Runner。

    设计理念：
    - 不直接绑死到某个 Planner 实现；
    - 将“如何从 EvalTask 调用具体 planner”的逻辑放在 planner_fn 里；
    - 默认提供一个 stub_planner_fn，至少 pipeline 可以跑通。
    """

    def __init__(
        self,
        *,
        eval_harness: Optional[EvalHarness] = None,
        planner_fn: Optional[PlannerFn] = None,
    ) -> None:
        try:
            self.eval_harness = eval_harness or EvalHarness(variants_runtimes={})
        except TypeError:
            self.eval_harness = eval_harness or EvalHarness()
        self.planner_fn = planner_fn or self._stub_planner_fn

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})

        dataset: Optional[EvalDatasetSpec] = ctx.get("planner_dataset") or ctx.get("eval_dataset")
        if dataset is None:
            logger.warning(
                "PlannerOfflineRunner: no EvalDatasetSpec provided in context "
                "(planner_dataset / eval_dataset missing). Using empty dataset."
            )
            dataset = EvalDatasetSpec(
                dataset_id="empty",
                name="empty",
                description="Empty dataset (no tasks).",
                component="planner",
                tasks=[],
            )

        if dataset.component != "planner":
            logger.warning(
                "PlannerOfflineRunner: dataset.component=%s but runner is for planner.",
                dataset.component,
            )

        def _eval_fn(task: EvalTaskSpec, variant_cfg: VariantConfig, local_ctx: Dict[str, Any]) -> Dict[str, Any]:
            return self.planner_fn(task, variant_cfg, local_ctx)

        return self.eval_harness.run_dataset(
            experiment=experiment,
            variant=variant,
            dataset=dataset,
            eval_fn=_eval_fn,
            context=ctx,
        )

    # ---------- 默认 stub planner ---------- #

    def _stub_planner_fn(
        self,
        task: EvalTaskSpec,
        variant: VariantConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        一个简单的 stub 实现，目的是让 pipeline 能跑通。

        行为：
        - 如果 expected_output 里有非空 "reference_plan"，则认为 success=True, score=1.0；
        - 否则 success=False, score=0.0。

        实际项目中，你应该替换为：
        - 调用真正的 CognitiveLoop._run_planner 或 planner 策略；
        - 解析 planner 输出，将其与 expected_output 对比打分。
        """
        expected = task.expected_output or {}
        has_ref_plan = bool(expected.get("reference_plan"))

        success = has_ref_plan
        score = 1.0 if has_ref_plan else 0.0

        return {
            "success": success,
            "score": score,
            "notes": "stub_planner_fn used; replace with real planner integration.",
            "used_stub": True,
            "task_id": task.task_id,
            "variant_id": variant.variant_id,
        }
