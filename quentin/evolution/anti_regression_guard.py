from __future__ import annotations
from typing import Dict, Any

class AntiRegressionGuard:
    """
    P8-C: Anti-regression Guard
    Blocks promotion if risks rise or gains are non-significant.
    """
    def check_promotion(self, candidate_metrics: Dict[str, float], baseline_metrics: Dict[str, float]) -> bool:
        """
        Return True if candidate is safe to promote.
        """
        # 1. Quality must not regress by > 2%
        if candidate_metrics.get("quality", 1.0) < baseline_metrics.get("quality", 1.0) * 0.98:
            return False
            
        # 2. Safety must not regress at all
        if candidate_metrics.get("safety", 1.0) < baseline_metrics.get("safety", 1.0):
            return False
            
        # 3. Must have significant gain in either cost or latency (e.g. > 5%)
        cost_gain = (baseline_metrics.get("cost", 1.0) - candidate_metrics.get("cost", 1.0)) / baseline_metrics.get("cost", 1.0)
        lat_gain = (baseline_metrics.get("latency", 1.0) - candidate_metrics.get("latency", 1.0)) / baseline_metrics.get("latency", 1.0)
        
        if cost_gain < 0.05 and lat_gain < 0.05:
            return False
            
        return True
