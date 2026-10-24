from __future__ import annotations

from app.models import EnergyVector


class FailureClassifier:
    def classify(self, energy: EnergyVector) -> str:
        failing = set(energy.failing_invariants)
        blame = set(energy.blame_candidates)

        if "module_has_owner" in failing or any(candidate.startswith("ownership") for candidate in blame):
            return "ownership_violation"
        if any("schema" in name or "contract" in name or "interface" in name for name in [*failing, *blame]):
            return "contract_drift"
        if any("build" in name or "compile" in name for name in blame):
            return "build_failure"
        if any("integration" in name or "unit" in name or "regression" in name for name in blame):
            return "implementation_bug"
        return "generic_failure"
