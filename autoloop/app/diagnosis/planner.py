from __future__ import annotations

from app.diagnosis.blame import BlameRanker
from app.diagnosis.classifier import FailureClassifier
from app.models import EnergyVector, RepairDecision, RollbackTargetLayer


class RepairPlanner:
    def __init__(
        self,
        classifier: FailureClassifier | None = None,
        blame_ranker: BlameRanker | None = None,
    ) -> None:
        self.classifier = classifier or FailureClassifier()
        self.blame_ranker = blame_ranker or BlameRanker()

    def plan(self, energy: EnergyVector) -> RepairDecision:
        failure_class = self.classifier.classify(energy)
        ranked_blame = self.blame_ranker.rank(energy)

        if failure_class == "ownership_violation":
            return RepairDecision(
                run_id=energy.run_id,
                phase_id=energy.phase_id,
                failure_class=failure_class,
                rollback_target_layer=RollbackTargetLayer.SPEC,
                rollback_scope=ranked_blame or [energy.module_id],
                affected_modules=[energy.module_id],
                required_agents=["lead", "planner"],
                repair_strategy="repair ownership or spec facts and regenerate task packets",
                confidence=0.95,
                scope_source="ownership_invariant",
                scope_confidence=0.95,
            )
        if failure_class == "contract_drift":
            return RepairDecision(
                run_id=energy.run_id,
                phase_id=energy.phase_id,
                failure_class=failure_class,
                rollback_target_layer=RollbackTargetLayer.CONTRACT,
                rollback_scope=ranked_blame or [energy.module_id],
                affected_modules=[energy.module_id],
                required_agents=["planner", "dev", "qa"],
                repair_strategy="rebuild contracts and re-render task packets before rerun",
                confidence=0.85,
                scope_source="contract_or_schema_signal",
                scope_confidence=0.85,
            )
        if failure_class in {"build_failure", "implementation_bug", "generic_failure"}:
            return RepairDecision(
                run_id=energy.run_id,
                phase_id=energy.phase_id,
                failure_class=failure_class,
                rollback_target_layer=RollbackTargetLayer.IMPLEMENTATION,
                rollback_scope=ranked_blame or [energy.module_id],
                affected_modules=[energy.module_id],
                required_agents=["dev", "qa"],
                repair_strategy="rollback implementation scope and rerun dev and qa",
                confidence=0.75,
                scope_source="build_or_test_signal",
                scope_confidence=0.75,
            )
        return RepairDecision(
            run_id=energy.run_id,
            phase_id=energy.phase_id,
            failure_class=failure_class,
            rollback_target_layer=RollbackTargetLayer.TASK,
            rollback_scope=ranked_blame or [energy.module_id],
            affected_modules=[energy.module_id],
            required_agents=["lead", "planner"],
            repair_strategy="rebuild task packet and rerun module",
            confidence=0.6,
            scope_source="generic_fallback",
            scope_confidence=0.6,
        )
