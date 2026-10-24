from app.control import EnergyScorer
from app.models import GateResult, GateStatus, GateSuiteResult, OverlapRisk
from app.sor import InvariantReport, InvariantViolation


def build_gate_suite(*results: GateResult) -> GateSuiteResult:
    return GateSuiteResult(
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_alpha",
        results=list(results),
    )


def test_hard_fail_gate_forces_hard_fail_energy():
    scorer = EnergyScorer()
    gate_suite = build_gate_suite(
        GateResult(gate_name="unit_tests", status=GateStatus.FAIL, hard_fail=True, score=0.0)
    )
    energy = scorer.from_gate_suite(gate_suite, InvariantReport(valid=True, violations=[]))
    assert energy.hard_fail is True
    assert energy.recommended_action.value == "halt"


def test_overlap_risk_penalizes_weighted_score():
    scorer = EnergyScorer()
    normal_suite = build_gate_suite(
        GateResult(gate_name="unit_tests", status=GateStatus.PASS, score=1.0)
    )
    overlap_suite = build_gate_suite(
        GateResult(gate_name="unit_tests", status=GateStatus.PASS, score=1.0),
        GateResult(gate_name="overlap_guard", status=GateStatus.WARN, score=0.9),
    )

    normal = scorer.from_gate_suite(normal_suite, InvariantReport(valid=True, violations=[]))
    overlap = scorer.from_gate_suite(overlap_suite, InvariantReport(valid=True, violations=[]))

    assert normal.overlap_risk == OverlapRisk.NONE
    assert overlap.overlap_risk == OverlapRisk.MEDIUM
    assert overlap.weighted_score < normal.weighted_score


def test_unresolved_failures_increase_penalty():
    scorer = EnergyScorer()
    gate_suite = build_gate_suite(
        GateResult(gate_name="build", status=GateStatus.FAIL, score=0.2),
        GateResult(gate_name="unit_tests", status=GateStatus.FAIL, score=0.1),
    )
    energy = scorer.from_gate_suite(
        gate_suite,
        InvariantReport(
            valid=False,
            violations=[
                InvariantViolation(
                    rule_id="module_has_owner",
                    level="error",
                    message="missing owner",
                    subject_id="module_alpha",
                )
            ],
        ),
    )
    assert energy.unresolved_failures == 2
    assert energy.weighted_score < 0.2
