from __future__ import annotations

from app.models import ConvergenceAction, ConvergenceDecision, EnergyVector


class DecisionPolicy:
    def __init__(self, score_threshold: float = 0.85, stagnation_epsilon: float = 0.02) -> None:
        self.score_threshold = score_threshold
        self.stagnation_epsilon = stagnation_epsilon

    def decide(
        self,
        previous: EnergyVector | None,
        current: EnergyVector,
    ) -> ConvergenceDecision:
        if current.hard_fail:
            decision = ConvergenceAction.HALT
        elif current.weighted_score >= self.score_threshold and current.unresolved_failures == 0:
            decision = ConvergenceAction.ADVANCE
        elif previous is None or current.weighted_score > previous.weighted_score + self.stagnation_epsilon:
            decision = ConvergenceAction.RETRY
        else:
            decision = ConvergenceAction.DIAGNOSE

        return ConvergenceDecision(
            run_id=current.run_id,
            phase_id=current.phase_id,
            decision=decision,
            hard_fail=current.hard_fail,
            failing_invariants=current.failing_invariants,
            blame_candidates=current.blame_candidates,
            energy=current,
        )
