from app.control import DecisionPolicy
from app.models import EnergyAction, EnergyVector


def build_energy(
    *,
    weighted_score: float,
    hard_fail: bool = False,
    unresolved_failures: int = 0,
    failing_invariants: list[str] | None = None,
    recommended_action: EnergyAction = EnergyAction.ADVANCE,
) -> EnergyVector:
    return EnergyVector(
        energy_id="energy_01",
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_alpha",
        weighted_score=weighted_score,
        hard_fail=hard_fail,
        unresolved_failures=unresolved_failures,
        failing_invariants=failing_invariants or [],
        recommended_action=recommended_action,
    )


def test_policy_halts_on_hard_fail():
    decision = DecisionPolicy().decide(
        previous=None,
        current=build_energy(
            weighted_score=0.2,
            hard_fail=True,
            failing_invariants=["module_has_owner"],
            recommended_action=EnergyAction.HALT,
        ),
    )
    assert decision.decision.value == "halt"


def test_policy_advances_when_threshold_passes():
    decision = DecisionPolicy(score_threshold=0.8).decide(
        previous=None,
        current=build_energy(weighted_score=0.92),
    )
    assert decision.decision.value == "advance"


def test_policy_retries_when_score_improves_but_below_threshold():
    previous = build_energy(weighted_score=0.55, recommended_action=EnergyAction.RETRY_MODULE)
    current = build_energy(weighted_score=0.7, recommended_action=EnergyAction.RETRY_MODULE)
    decision = DecisionPolicy(score_threshold=0.85).decide(previous=previous, current=current)
    assert decision.decision.value == "retry"


def test_policy_diagnoses_when_score_stagnates():
    previous = build_energy(weighted_score=0.7, recommended_action=EnergyAction.DIAGNOSE)
    current = build_energy(weighted_score=0.69, recommended_action=EnergyAction.DIAGNOSE)
    decision = DecisionPolicy(score_threshold=0.85).decide(previous=previous, current=current)
    assert decision.decision.value == "diagnose"
