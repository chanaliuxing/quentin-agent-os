from __future__ import annotations

from app.control.calibration import EnergyCalibrator
from app.models import EnergyAction, EnergyVector, GateSuiteResult, OverlapRisk
from app.sor.validator import InvariantReport


class EnergyScorer:
    def __init__(self, score_floor: float = 0.0, calibrator: EnergyCalibrator | None = None) -> None:
        self.score_floor = score_floor
        self.calibrator = calibrator or EnergyCalibrator()

    def from_gate_suite(
        self,
        gate_suite: GateSuiteResult,
        invariant_report: InvariantReport,
    ) -> EnergyVector:
        gate_scores = [result.score for result in gate_suite.results]
        base_score = sum(gate_scores) / len(gate_scores) if gate_scores else 1.0
        overlap_risk = self._infer_overlap_risk(gate_suite)
        unresolved_failures = sum(1 for result in gate_suite.results if result.status.value == "fail")
        overlap_penalty = self.calibrator.overlap_penalty(overlap_risk.value)
        invariant_penalty = self.calibrator.invariant_penalty() * len(invariant_report.violations)
        unresolved_penalty = self.calibrator.unresolved_failure_penalty() * unresolved_failures
        weighted_score = max(
            self.score_floor,
            min(1.0, base_score - overlap_penalty - invariant_penalty - unresolved_penalty),
        )
        hard_fail = any(result.hard_fail for result in gate_suite.results) or not invariant_report.valid
        failing_invariants = [
            *invariant_report.failing_invariants,
            *[result.gate_name for result in gate_suite.results if result.hard_fail],
        ]
        blame_candidates = [
            *[violation.subject_id for violation in invariant_report.violations],
            *[result.gate_name for result in gate_suite.results if result.status.value == "fail"],
        ]
        recommended_action = self._recommended_action(
            hard_fail=hard_fail,
            weighted_score=weighted_score,
            unresolved_failures=unresolved_failures,
        )
        return EnergyVector(
            energy_id=f"energy_{gate_suite.phase_id}_{gate_suite.module_id}",
            run_id=gate_suite.run_id,
            phase_id=gate_suite.phase_id,
            module_id=gate_suite.module_id,
            schema_valid=self._gate_is_passing(gate_suite, "schema"),
            build_valid=self._gate_is_passing(gate_suite, "build"),
            unit_valid=self._gate_is_passing(gate_suite, "unit"),
            integration_valid=self._gate_is_passing(gate_suite, "integration"),
            regression_valid=self._gate_is_passing(gate_suite, "regression"),
            sor_invariants_valid=invariant_report.valid,
            ownership_valid=not any(
                violation.rule_id == "module_has_owner" for violation in invariant_report.violations
            ),
            provenance_complete=self._gate_is_passing(gate_suite, "provenance"),
            overlap_risk=overlap_risk,
            unresolved_failures=unresolved_failures,
            weighted_score=weighted_score,
            hard_fail=hard_fail,
            failing_invariants=failing_invariants,
            gate_results=gate_suite.results,
            blame_candidates=blame_candidates,
            recommended_action=recommended_action,
        )

    def update_calibration(self, *, weighted_score: float, succeeded: bool) -> None:
        self.calibrator.update(weighted_score=weighted_score, succeeded=succeeded)

    def _infer_overlap_risk(self, gate_suite: GateSuiteResult) -> OverlapRisk:
        overlap_results = [
            result for result in gate_suite.results if "overlap" in result.gate_name.lower()
        ]
        if not overlap_results:
            return OverlapRisk.NONE
        statuses = {result.status.value for result in overlap_results}
        if "fail" in statuses:
            return OverlapRisk.HIGH
        if "warn" in statuses:
            return OverlapRisk.MEDIUM
        return OverlapRisk.LOW

    def _gate_is_passing(self, gate_suite: GateSuiteResult, prefix: str) -> bool:
        matching = [
            result for result in gate_suite.results if result.gate_name.lower().startswith(prefix)
        ]
        if not matching:
            return True
        return all(result.status.value != "fail" for result in matching)

    def _recommended_action(
        self,
        *,
        hard_fail: bool,
        weighted_score: float,
        unresolved_failures: int,
    ) -> EnergyAction:
        if hard_fail:
            return EnergyAction.HALT
        if unresolved_failures == 0 and weighted_score >= 0.85:
            return EnergyAction.ADVANCE
        if weighted_score >= 0.5:
            return EnergyAction.RETRY_MODULE
        return EnergyAction.DIAGNOSE
