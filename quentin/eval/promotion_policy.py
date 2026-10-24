from __future__ import annotations
from typing import Dict, Any, List, Optional
from quentin.eval.experiment_hub import ExperimentHub

class PromotionPolicy:
    """
    P6-C: Promotion Policy
    Decides if an experiment result is good enough to be promoted.
    """
    def __init__(self, hub: ExperimentHub) -> None:
        self.hub = hub
        self.thresholds: Dict[str, float] = {
            "success_rate": 0.95,
            "quality_score": 0.8
        }

    def can_promote(self, experiment_id: str) -> bool:
        summary = self.hub.get_summary(experiment_id)
        if not summary:
            return False
        
        for metric, threshold in self.thresholds.items():
            val = summary.get(metric)
            if val is not None and val < threshold:
                return False
        
        return True
