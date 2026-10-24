from __future__ import annotations
from quentin.optimization.multi_objective_controller import OptimizationWeights

class WeightAdaptationEngine:
    """
    P8-B: Weight Adaptation Engine
    Adjusts weights based on system state (e.g., error budget exhaustion).
    """
    def adapt_weights(self, current_weights: OptimizationWeights, system_state: Dict[str, Any]) -> OptimizationWeights:
        new_weights = OptimizationWeights(
            quality=current_weights.quality,
            safety=current_weights.safety,
            cost=current_weights.cost,
            latency=current_weights.latency
        )
        
        # Scenario: Error budget low -> prioritize safety
        if system_state.get("error_budget_percentage", 1.0) < 0.2:
            new_weights.safety += 0.2
            new_weights.quality -= 0.1
            new_weights.cost -= 0.1
            
        # Scenario: High latency complaints -> prioritize latency
        if system_state.get("p95_latency_ms", 0) > 5000:
            new_weights.latency += 0.2
            new_weights.cost -= 0.2
            
        return new_weights
