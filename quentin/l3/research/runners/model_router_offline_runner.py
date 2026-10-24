# quentin/l3/research/runners/model_router_offline_runner.py
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
from quentin.routing.model_router import ModelRouter, ModelRouteRequest

logger = logging.getLogger(__name__)

# model_router_fn: (task, variant, context) -> dict with keys: success, score, chosen_model, etc.
ModelRouterFn = Callable[[EvalTaskSpec, VariantConfig, Dict[str, Any]], Dict[str, Any]]


class ModelRouterOfflineRunner(ExperimentRunner):
    """
    针对 ModelRouter 组件的离线评测 Runner。

    设计理念：
    - 不直接绑死到某个 ModelRouter 实现；
    - 将“如何从 EvalTask 调用具体 ModelRouter”的逻辑放在 model_router_fn 里；
    - 默认提供一个 stub_model_router_fn，至少 pipeline 可以跑通。
    """

    def __init__(
        self,
        *,
        eval_harness: Optional[EvalHarness] = None,
        model_router_fn: Optional[ModelRouterFn] = None,
    ) -> None:
        try:
            self.eval_harness = eval_harness or EvalHarness(variants_runtimes={})
        except TypeError:
            self.eval_harness = eval_harness or EvalHarness()
        self.model_router_fn = model_router_fn or self._default_model_router_fn

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})

        dataset: Optional[EvalDatasetSpec] = ctx.get("model_router_dataset") or ctx.get("eval_dataset")
        if dataset is None:
            logger.warning(
                "ModelRouterOfflineRunner: no EvalDatasetSpec provided in context "
                "(model_router_dataset / eval_dataset missing). Using empty dataset."
            )
            dataset = EvalDatasetSpec(
                dataset_id="empty",
                name="empty",
                description="Empty dataset (no tasks).",
                component="model_router",
                tasks=[],
            )

        if dataset.component != "model_router":
            logger.warning(
                "ModelRouterOfflineRunner: dataset.component=%s but runner is for model_router.",
                dataset.component,
            )

        def _eval_fn(task: EvalTaskSpec, variant_cfg: VariantConfig, local_ctx: Dict[str, Any]) -> Dict[str, Any]:
            return self.model_router_fn(task, variant_cfg, local_ctx)

        return self.eval_harness.run_dataset(
            experiment=experiment,
            variant=variant,
            dataset=dataset,
            eval_fn=_eval_fn,
            context=ctx,
        )

    def _default_model_router_fn(
        self,
        task: EvalTaskSpec,
        variant: VariantConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Default integration: route using canonical `quentin.routing.model_router.ModelRouter`.

        Uses `variant.params` as base_config overrides (safe defaults are applied by the router).
        """
        expected = task.expected_output or {}
        expected_model = expected.get("chosen_model")
        payload = task.input_payload or {}
        req = ModelRouteRequest(
            task_type=str(payload.get("task_type") or task.task_id),
            importance=str(payload.get("importance") or "normal"),
            domain=str(payload.get("domain") or context.get("domain") or "general"),
            constraints=dict(payload.get("constraints") or {}),
            metadata={"eval_task_id": task.task_id, "variant_id": variant.variant_id},
        )

        router = ModelRouter(base_config=variant.params or {})
        decision = router.route(req)
        chosen_model = decision.model_id

        success = (chosen_model == expected_model) if expected_model else True
        score = 1.0 if success else 0.0

        return {
            "success": success,
            "score": score,
            "chosen_model": chosen_model,
            "notes": "canonical ModelRouter used.",
            "used_stub": False,
            "task_id": task.task_id,
            "variant_id": variant.variant_id,
        }
