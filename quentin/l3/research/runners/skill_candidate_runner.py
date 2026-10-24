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
from quentin.skills.store import SkillStore
from quentin.skills.schema import SkillCandidate

logger = logging.getLogger(__name__)


class SkillCandidateRunner(ExperimentRunner):
    """
    针对 SkillCandidate 的离线评测 Runner（stub 版）。

    用法：
    - ExperimentConfig.target_component = "skill_candidate"
    - VariantConfig.params:
        - "skill_candidate_id": str
    - context:
        - 预留 "eval_dataset" / "task_factory" 等，未来可扩展为真正的行为测试
    """

    def __init__(
        self,
        engine: SelfProgrammingEngine,
        *,
        skill_store: Optional[SkillStore] = None,
    ) -> None:
        self.engine = engine
        self.skill_store = skill_store or engine.skill_store

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})
        candidate_id = variant.params.get("skill_candidate_id")

        if not candidate_id:
            logger.warning(
                "SkillCandidateRunner: variant=%s has no skill_candidate_id",
                variant.variant_id,
            )
            metrics = {
                "score": 0.0,
                "has_test_cases": 0.0,
                "estimated_risk": 1.0,
            }
            extra = {
                "candidate": None,
                "error": "missing skill_candidate_id",
            }
            return VariantResult(
                variant_id=variant.variant_id,
                metrics=metrics,
                extra=extra,
            )

        cand = self.skill_store.load_candidate(candidate_id)
        if cand is None:
            logger.warning(
                "SkillCandidateRunner: skill_candidate_id=%s not found",
                candidate_id,
            )
            metrics = {
                "score": 0.0,
                "has_test_cases": 0.0,
                "estimated_risk": 1.0,
            }
            extra = {
                "candidate": None,
                "error": "candidate not found",
            }
            return VariantResult(
                variant_id=variant.variant_id,
                metrics=metrics,
                extra=extra,
            )

        # v1 stub：简单按照是否有 test_cases 来打分
        has_tests = len(cand.proposed_skill.test_cases) > 0
        has_tests_float = 1.0 if has_tests else 0.0

        # 估算风险：有测试则略低
        estimated_risk = 0.8 if has_tests else 1.0
        score = has_tests_float * (1.0 - estimated_risk * 0.5)

        metrics = {
            "score": float(score),
            "has_test_cases": has_tests_float,
            "estimated_risk": float(estimated_risk),
        }

        extra = {
            "candidate": cand.to_dict(),
        }

        return VariantResult(
            variant_id=variant.variant_id,
            metrics=metrics,
            extra=extra,
        )
