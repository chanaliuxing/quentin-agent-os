from app.control import DecisionPolicy
from app.diagnosis import RepairPlanner
from app.models import EnergyAction, EnergyVector, RollbackTargetLayer
from app.temporal.workflow import _execute_temporal_repair


def build_energy(
    *,
    weighted_score: float,
    blame_candidates: list[str],
    hard_fail: bool = False,
    failing_invariants: list[str] | None = None,
) -> EnergyVector:
    return EnergyVector(
        energy_id=f"energy_{weighted_score}",
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_a",
        weighted_score=weighted_score,
        hard_fail=hard_fail,
        failing_invariants=failing_invariants or ([] if not hard_fail else ["generic_failure"]),
        blame_candidates=blame_candidates,
        recommended_action=EnergyAction.DIAGNOSE,
    )


def test_retry_flow_routes_to_implementation_repair():
    previous = build_energy(weighted_score=0.40, blame_candidates=["build_compile"])
    current = build_energy(weighted_score=0.70, blame_candidates=["build_compile"])
    decision = DecisionPolicy(score_threshold=0.85).decide(previous=previous, current=current)
    repair = RepairPlanner().plan(current)
    pending_modules, execution = _execute_temporal_repair(
        project_id="run_01",
        phase_id="phase_01",
        modules=[{"name": "module_a"}, {"name": "module_b"}],
        failed_modules=[{"name": "module_b"}],
        repair_decision=repair,
    )

    assert decision.decision.value == "retry"
    assert repair.rollback_target_layer == RollbackTargetLayer.IMPLEMENTATION
    assert repair.scope_source == "build_or_test_signal"
    assert repair.scope_confidence == 0.75
    assert execution["next_action"] == "dispatch_dev"
    assert pending_modules == [{"name": "module_b"}]


def test_diagnose_flow_routes_to_contract_repair():
    previous = build_energy(weighted_score=0.65, blame_candidates=["schema_contract"])
    current = build_energy(weighted_score=0.63, blame_candidates=["schema_contract"])
    decision = DecisionPolicy(score_threshold=0.85).decide(previous=previous, current=current)
    repair = RepairPlanner().plan(current)
    pending_modules, execution = _execute_temporal_repair(
        project_id="run_01",
        phase_id="phase_01",
        modules=[{"name": "module_a"}, {"name": "module_b"}],
        failed_modules=[],
        repair_decision=repair,
    )

    assert decision.decision.value == "diagnose"
    assert repair.rollback_target_layer == RollbackTargetLayer.CONTRACT
    assert repair.scope_source == "contract_or_schema_signal"
    assert repair.scope_confidence == 0.85
    assert execution["next_action"] == "lead_plan"
    assert pending_modules == [{"name": "module_a"}, {"name": "module_b"}]


def test_halt_flow_maps_ownership_violation_to_spec_repair():
    current = build_energy(
        weighted_score=0.20,
        blame_candidates=["ownership_overlap"],
        hard_fail=True,
        failing_invariants=["module_has_owner"],
    )
    decision = DecisionPolicy(score_threshold=0.85).decide(previous=None, current=current)
    repair = RepairPlanner().plan(current)
    pending_modules, execution = _execute_temporal_repair(
        project_id="run_01",
        phase_id="phase_01",
        modules=[{"name": "module_a"}, {"name": "module_b"}],
        failed_modules=[{"name": "module_a"}],
        repair_decision=repair,
    )

    assert decision.decision.value == "halt"
    assert repair.rollback_target_layer == RollbackTargetLayer.SPEC
    assert repair.scope_source == "ownership_invariant"
    assert repair.scope_confidence == 0.95
    assert execution["next_action"] == "lead_plan"
    assert pending_modules == [{"name": "module_a"}, {"name": "module_b"}]
