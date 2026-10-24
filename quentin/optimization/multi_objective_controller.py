from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class OptimizationWeights:
    quality: float = 0.4
    safety: float = 0.3
    cost: float = 0.2
    latency: float = 0.1

class MultiObjectiveController:
    """
    P8-B: Multi-objective Optimization Controller
    Balances competing goals (QSCV) using dynamic weighting.
    """
    def __init__(self, initial_weights: Optional[OptimizationWeights] = None) -> None:
        self.weights = initial_weights or OptimizationWeights()

    def evaluate_proposal(self, candidate_metrics: Dict[str, float]) -> float:
        """
        Calculate a scalar utility score for a candidate.
        """
        score = (
            self.weights.quality * candidate_metrics.get("quality", 0.0) +
            self.weights.safety * candidate_metrics.get("safety", 0.0) -
            self.weights.cost * candidate_metrics.get("cost_normalized", 0.0) -
            self.weights.latency * candidate_metrics.get("latency_normalized", 0.0)
        )
        return score

    def update_weights(self, new_weights: OptimizationWeights) -> None:
        self.weights = new_weights
