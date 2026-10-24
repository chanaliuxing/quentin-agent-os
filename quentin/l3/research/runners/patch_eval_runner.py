# quentin/l3/research/runners/patch_eval_runner.py
from __future__ import annotations

from typing import Any, Dict, Optional, Callable
import logging
import importlib
import os
from types import ModuleType

from quentin.l3.research.orchestrator import ExperimentRunner
from quentin.l3.research.experiments import (
    ExperimentConfig,
    VariantConfig,
    VariantResult,
)
from quentin.eval.spec import EvalDatasetSpec, EvalTaskSpec
from quentin.eval.harness import EvalHarness
from quentin.self_programming.schema import PatchCandidate, PatchReport, PatchTestResult # Need patch schema

logger = logging.getLogger(__name__)

# Function to run tests/evaluation for a given patch variant
PatchEvalFn = Callable[[EvalTaskSpec, VariantConfig, Dict[str, Any]], Dict[str, Any]]


class PatchEvalRunner(ExperimentRunner):
    """
    针对 Patch 的评测 Runner。

    用于评测新生成的 PatchCandidate 是否有效、安全、提升指标。
    """

    def __init__(
        self,
        *,
        eval_harness: Optional[EvalHarness] = None,
        patch_eval_fn: Optional[PatchEvalFn] = None,
    ) -> None:
        try:
            self.eval_harness = eval_harness or EvalHarness(variants_runtimes={})
        except TypeError:
            self.eval_harness = eval_harness or EvalHarness()
        allow_stub = os.getenv("ALLOW_STUB_RESEARCH_RUNNERS", "0").lower() in {"1", "true", "yes"}
        if patch_eval_fn is not None:
            self.patch_eval_fn = patch_eval_fn
        elif allow_stub:
            self.patch_eval_fn = self._stub_patch_eval_fn
        else:
            self.patch_eval_fn = self._disabled_patch_eval_fn

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})

        dataset: Optional[EvalDatasetSpec] = ctx.get("patch_dataset") or ctx.get("eval_dataset")
        if dataset is None:
            logger.warning(
                "PatchEvalRunner: no EvalDatasetSpec provided in context. Using empty dataset."
            )
            dataset = EvalDatasetSpec(
                dataset_id="empty_patch_eval",
                name="empty_patch_eval",
                description="Empty dataset for Patch Evaluation.",
                component="patch_eval",
                tasks=[],
            )

        if dataset.component != "patch_eval":
            logger.warning(
                "PatchEvalRunner: dataset.component=%s but runner is for patch_eval.",
                dataset.component,
            )

        def _eval_fn(task: EvalTaskSpec, variant_cfg: VariantConfig, local_ctx: Dict[str, Any]) -> Dict[str, Any]:
            return self.patch_eval_fn(task, variant_cfg, local_ctx)

        return self.eval_harness.run_dataset(
            experiment=experiment,
            variant=variant,
            dataset=dataset,
            eval_fn=_eval_fn,
            context=ctx,
        )

    # ---------- 默认 stub patch 评测逻辑 ---------- #
    def _disabled_patch_eval_fn(
        self,
        task: EvalTaskSpec,
        variant: VariantConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise RuntimeError(
            "PatchEvalRunner is disabled by default to avoid synthetic metrics. "
            "Provide patch_eval_fn or set ALLOW_STUB_RESEARCH_RUNNERS=1."
        )

    def _stub_patch_eval_fn(
        self,
        task: EvalTaskSpec,
        variant: VariantConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        stub 版评测逻辑：

        - 模拟 patch 的应用和测试。
        - 如果 variant 是 'baseline'，假定通过。
        - 如果 variant 是 'candidate'，根据 task.expected_output 模拟结果。
        """
        patch_id = task.metadata.get("patch_id")
        target_file = task.metadata.get("target_file")
        
        # In a real scenario, here you'd:
        # 1. Temporarily apply the patch_diff (from variant.params or context) to target_file.
        # 2. Run unit tests, static analysis, or even a mini-CognitiveLoop run.
        # 3. Collect metrics.
        
        success = False
        score = 0.0
        notes = f"Stub patch eval for {patch_id} variant {variant.variant_id}"

        if variant.variant_id == "baseline":
            success = True # Assume baseline is stable
            score = 1.0
            notes += ": baseline always succeeds in stub."
        elif variant.variant_id == "candidate":
            # For candidate, assume success if expected output hints at it.
            # Or if no expected output, just randomly succeed/fail.
            expected = task.expected_output or {}
            if expected.get("passed_tests"): # If expected_output has a 'passed_tests' flag
                success = bool(expected["passed_tests"])
                score = 1.0 if success else 0.0
                notes += ": candidate result based on expected_output."
            else:
                # Default for stub candidate without specific expectation
                success = True 
                score = 0.8
                notes += ": candidate stub simulation (default success)."
        
        return {
            "success": success,
            "score": score,
            "notes": notes,
            "patch_id": patch_id,
            "variant_id": variant.variant_id,
            "task_id": task.task_id,
        }
