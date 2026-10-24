from app.diagnosis import FailureClassifier, RepairPlanner
from app.models import EnergyAction, EnergyVector, RollbackTargetLayer


def build_energy(*, blame_candidates: list[str], failing_invariants: list[str] | None = None) -> EnergyVector:
    return EnergyVector(
        energy_id="energy_01",
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_alpha",
        weighted_score=0.4,
        blame_candidates=blame_candidates,
        failing_invariants=failing_invariants or ["integration_guard"],
        hard_fail=True,
        recommended_action=EnergyAction.HALT,
    )


def test_failure_classifier_maps_contract_drift():
    classifier = FailureClassifier()
    energy = build_energy(blame_candidates=["schema_contract"])
    assert classifier.classify(energy) == "contract_drift"


def test_repair_planner_maps_build_failure_to_implementation():
    planner = RepairPlanner()
    energy = build_energy(blame_candidates=["build_compile"])
    decision = planner.plan(energy)
    assert decision.rollback_target_layer == RollbackTargetLayer.IMPLEMENTATION
    assert decision.scope_source == "build_or_test_signal"
    assert decision.scope_confidence == 0.75


def test_repair_planner_maps_ownership_to_spec():
    planner = RepairPlanner()
    energy = build_energy(
        blame_candidates=["ownership_overlap"],
        failing_invariants=["module_has_owner"],
    )
    decision = planner.plan(energy)
    assert decision.rollback_target_layer == RollbackTargetLayer.SPEC
    assert decision.scope_source == "ownership_invariant"
    assert decision.scope_confidence == 0.95
