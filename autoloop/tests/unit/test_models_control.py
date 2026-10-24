import pytest
from pydantic import ValidationError

from app.models import (
    ConvergenceAction,
    ConvergenceDecision,
    EnergyAction,
    EnergyVector,
    RepairDecision,
    RollbackTargetLayer,
)


def test_energy_vector_rejects_invalid_overlap_risk():
    with pytest.raises(ValidationError):
        EnergyVector(
            energy_id="energy_01",
            run_id="run_01",
            phase_id="phase_01",
            module_id="module_alpha",
            weighted_score=0.8,
            overlap_risk="critical",
        )


def test_energy_vector_requires_failing_invariants_for_hard_fail():
    with pytest.raises(ValidationError):
        EnergyVector(
            energy_id="energy_01",
            run_id="run_01",
            phase_id="phase_01",
            module_id="module_alpha",
            weighted_score=0.2,
            hard_fail=True,
            recommended_action=EnergyAction.HALT,
        )


def test_repair_decision_limits_rollback_target_layer():
    decision = RepairDecision(
        run_id="run_01",
        phase_id="phase_01",
        failure_class="integration_failure",
        rollback_target_layer=RollbackTargetLayer.CONTRACT,
        rollback_scope=["module_alpha"],
        affected_modules=["module_alpha"],
        required_agents=["planner", "dev"],
        repair_strategy="recompile task packet and rerun",
        confidence=0.9,
    )
    assert decision.rollback_target_layer == RollbackTargetLayer.CONTRACT

    with pytest.raises(ValidationError):
        RepairDecision(
            run_id="run_01",
            phase_id="phase_01",
            failure_class="integration_failure",
            rollback_target_layer="workflow",
            rollback_scope=[],
            affected_modules=[],
            required_agents=[],
            repair_strategy="halt",
            confidence=0.2,
        )


def test_convergence_decision_keeps_energy_payload():
    energy = EnergyVector(
        energy_id="energy_01",
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_alpha",
        weighted_score=0.95,
    )
    decision = ConvergenceDecision(
        run_id="run_01",
        phase_id="phase_01",
        decision=ConvergenceAction.ADVANCE,
        energy=energy,
    )
    assert decision.energy.module_id == "module_alpha"
