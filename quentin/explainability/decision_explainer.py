from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Explanation:
    decision_id: str
    outcome: str
    factors: Dict[str, float] = field(default_factory=dict)
    policy_hits: List[str] = field(default_factory=list)
    narrative: str = ""

class DecisionExplainer:
    """
    P7-D: Decision Explainer
    Generates human-readable explanations for autonomous decisions.
    """
    def explain(self, context: Dict[str, Any], decision: Dict[str, Any]) -> Explanation:
        outcome = decision.get("action", "unknown")
        factors = {}
        
        # Heuristic explanation
        if decision.get("score"):
            factors["score"] = float(decision["score"])
        
        narrative = f"Decision to {outcome} was made based on factors: {list(factors.keys())}."
        
        return Explanation(
            decision_id=context.get("id", "unknown"),
            outcome=outcome,
            factors=factors,
            narrative=narrative
        )
