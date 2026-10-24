from __future__ import annotations
from typing import Dict, Any, List

class CalibrationEvaluator:
    """
    P9-D: Calibration Evaluator
    Compares policy intent vs actual outcomes.
    """
    def evaluate_policy_drift(self, policy_id: str, outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect if a policy is behaving differently than intended.
        """
        total = len(outcomes)
        violations = sum(1 for o in outcomes if o.get("violation"))
        
        drift_score = violations / total if total > 0 else 0.0
        
        return {
            "policy_id": policy_id,
            "drift_score": drift_score,
            "needs_tuning": drift_score > 0.05
        }
