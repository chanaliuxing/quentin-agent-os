from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from quentin.l3.research.orchestrator import ExperimentRunner
from quentin.l3.research.experiments import (
    ExperimentConfig,
    VariantConfig,
    VariantResult,
)
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.self_programming.store import PatchStore
from quentin.self_programming.schema import PatchCandidate, PatchReport

logger = logging.getLogger(__name__)


class PatchTestRunner(ExperimentRunner):
    """
    针对 PatchCandidate 的实验 Runner。

    设计思路：
    - 每个 variant 对应一个 patch_id（或 "baseline"）
    - 调用 SelfProgrammingEngine.run_tests_for_patch()
    - 把 PatchReport 映射到 VariantResult.metrics

    用法：
    - ExperimentConfig.target_component = "patch_test"
    - VariantConfig.params:
        - "patch_id": str   # PatchCandidate ID
    - context 可选字段：
        - "test_suites": ["unit", "static_analysis", ...]
        - "extra_context": dict
    """

    def __init__(
        self,
        engine: SelfProgrammingEngine,
        *,
        patch_store: Optional[PatchStore] = None,
    ) -> None:
        self.engine = engine
        self.patch_store = patch_store or engine.patch_store

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})
        test_suites = ctx.get("test_suites") or ["unit", "static_analysis"]
        extra_ctx = ctx.get("extra_context") or {}

        patch_id = variant.params.get("patch_id")
        if not patch_id:
            # baseline 或无 patch 情况
            logger.info(
                "PatchTestRunner: variant=%s has no patch_id; treated as baseline.",
                variant.variant_id,
            )
            metrics = {
                "score": 0.0,
                "tests_passed_ratio": 0.0,
                "risk_score": 0.0,
            }
            extra = {
                "patch_report": None,
                "is_baseline": True,
            }
            return VariantResult(
                variant_id=variant.variant_id,
                metrics=metrics,
                extra=extra,
            )

        patch = self.patch_store.load_candidate(patch_id)
        if patch is None:
            logger.warning(
                "PatchTestRunner: patch_id=%s not found for variant=%s",
                patch_id,
                variant.variant_id,
            )
            metrics = {
                "score": 0.0,
                "tests_passed_ratio": 0.0,
                "risk_score": 1.0,
            }
            extra = {
                "patch_report": None,
                "error": f"patch_id={patch_id} not found",
            }
            return VariantResult(
                variant_id=variant.variant_id,
                metrics=metrics,
                extra=extra,
            )

        report: PatchReport = self.engine.run_tests_for_patch(
            patch=patch,
            test_suites=test_suites,
            extra_context=extra_ctx,
        )

        # 根据 PatchReport 计算简单指标
        total_tests = len(report.tests) or 1
        passed_tests = sum(1 for t in report.tests if t.passed)
        passed_ratio = passed_tests / total_tests

        # v1：score 先简单用 (passed_ratio * (1 - risk_score))
        risk_score = float(report.risk_score or 1.0)
        score = passed_ratio * max(0.0, 1.0 - risk_score)

        metrics = {
            "score": float(score),
            "tests_passed_ratio": float(passed_ratio),
            "risk_score": float(risk_score),
            "coverage": float(report.coverage or 0.0),
        }

        extra = {
            "patch_report": report.to_dict(),
            "patch_id": patch_id,
        }

        return VariantResult(
            variant_id=variant.variant_id,
            metrics=metrics,
            extra=extra,
        )
