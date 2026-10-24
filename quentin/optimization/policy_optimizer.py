from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class OptimizationTarget:
    metric: str
    direction: str # "minimize", "maximize"
    weight: float = 1.0

@dataclass
class Constraint:
    metric: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None

class PolicyOptimizer:
    """
    P4-C: Policy Optimizer
    Optimizes system policies (e.g., routing) for cost, latency, and quality.
    """
    def __init__(self) -> None:
        self.targets = [
            OptimizationTarget("cost", "minimize"),
            OptimizationTarget("latency_p95", "minimize")
        ]
        self.constraints = [
            Constraint("success_rate", min_value=0.95),
            Constraint("quality_score", min_value=0.8)
        ]

    def optimize(self, current_policy: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Suggest updates to the policy based on metrics.
        """
        new_policy = current_policy.copy()
        
        # Check constraints
        for constraint in self.constraints:
            val = metrics.get(constraint.metric)
            if val is not None:
                if constraint.min_value is not None and val < constraint.min_value:
                    # Constraint violated, might need to revert or harden
                    return self._harden_policy(current_policy, constraint.metric)
        
        # Optimization logic (heuristic for now)
        cost = metrics.get("cost", 0)
        latency = metrics.get("latency_p95", 0)
        
        if cost > 1.0: # arbitrary high cost
             new_policy["preference"] = "cost"
        elif latency > 5000: # arbitrary high latency
             new_policy["preference"] = "speed"
        else:
             new_policy["preference"] = "balanced"
             
        return new_policy

    def _harden_policy(self, policy: Dict[str, Any], reason: str) -> Dict[str, Any]:
        # Switch to safer/higher quality models if quality constraints fail
        new_policy = policy.copy()
        new_policy["preference"] = "quality"
        new_policy["harden_reason"] = reason
        return new_policy
