# quentin/l3/research/runners/skill_evolution_runner.py
from __future__ import annotations

from typing import Any, Dict, Optional, Callable
import logging
import os

from quentin.l3.research.orchestrator import ExperimentRunner
from quentin.l3.research.experiments import (
    ExperimentConfig,
    VariantConfig,
    VariantResult,
)
from quentin.eval.spec import EvalDatasetSpec
from quentin.eval.harness import EvalHarness

logger = logging.getLogger(__name__)

SkillEvolutionFn = Callable[[Any, VariantConfig, Dict[str, Any]], Dict[str, Any]]


class SkillEvolutionRunner(ExperimentRunner):
    """
    针对 Skill Evolution 策略的离线评测 Runner。

    这个 Runner 用来评测不同的技能演化策略（例如：如何选择候选技能进行实现，
    如何设计实现过程中的 Prompt，或者如何在多个实现中做 A/B 测选择最佳）。

    它本身不直接执行技能，而是评测“生成/选择技能”这个过程。
    """

    def __init__(
        self,
        *,
        eval_harness: Optional[EvalHarness] = None,
        skill_evolution_fn: Optional[SkillEvolutionFn] = None,
    ) -> None:
        try:
            self.eval_harness = eval_harness or EvalHarness(variants_runtimes={})
        except TypeError:
            self.eval_harness = eval_harness or EvalHarness()
        allow_stub = os.getenv("ALLOW_STUB_RESEARCH_RUNNERS", "0").lower() in {"1", "true", "yes"}
        if skill_evolution_fn is not None:
            self.skill_evolution_fn = skill_evolution_fn
        elif allow_stub:
            self.skill_evolution_fn = self._stub_skill_evolution_fn
        else:
            self.skill_evolution_fn = self._disabled_skill_evolution_fn

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})

        dataset: Optional[EvalDatasetSpec] = ctx.get("skill_evolution_dataset") or ctx.get("eval_dataset")
        if dataset is None:
            logger.warning(
                "SkillEvolutionRunner: no EvalDatasetSpec provided in context. Using empty dataset."
            )
            dataset = EvalDatasetSpec(
                dataset_id="empty",
                name="empty",
                description="Empty dataset (no tasks).",
                component="skill_evolution",
                tasks=[],
            )

        if dataset.component != "skill_evolution":
            logger.warning(
                "SkillEvolutionRunner: dataset.component=%s but runner is for skill_evolution.",
                dataset.component,
            )

        payload = self.skill_evolution_fn(dataset, variant, ctx) or {}
        metrics = dict(payload.get("metrics") or {})
        extra = dict(payload.get("extra") or {})
        if "score" not in metrics:
            metrics["score"] = float(metrics.get("avg_score") or metrics.get("success_rate") or 0.0)

        return VariantResult(
            variant_id=variant.variant_id,
            metrics=metrics,
            extra=extra,
        )

    def _disabled_skill_evolution_fn(self, dataset: Any, variant: VariantConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError(
            "SkillEvolutionRunner is disabled by default to avoid synthetic metrics. "
            "Provide skill_evolution_fn or set ALLOW_STUB_RESEARCH_RUNNERS=1."
        )

    def _stub_skill_evolution_fn(self, dataset: Any, variant: VariantConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        total_tasks = len(getattr(dataset, "tasks", []) or [])
        if total_tasks > 0:
            success_rate = float(variant.params.get("simulated_success_rate", 0.7))
            avg_score = float(variant.params.get("simulated_avg_score", 0.8))
        else:
            success_rate = 0.0
            avg_score = 0.0

        return {
            "metrics": {
                "success_rate": success_rate,
                "avg_score": avg_score,
                "score": avg_score,
            },
            "extra": {
                "dataset_id": getattr(dataset, "dataset_id", "unknown"),
                "num_tasks": total_tasks,
                "notes": "stub_skill_evolution_runner used (ALLOW_STUB_RESEARCH_RUNNERS=1).",
                "used_stub": True,
            },
        }
