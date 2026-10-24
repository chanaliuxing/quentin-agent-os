from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

@dataclass
class ExperimentResult:
    experiment_id: str
    metrics: Dict[str, float]
    status: str # "completed", "failed"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class ExperimentHub:
    """
    P6-C: Experiment Hub
    Aggregates offline evaluation and online A/B results.
    """
    def __init__(self) -> None:
        self.results: Dict[str, List[ExperimentResult]] = {}

    def record_result(self, experiment_id: str, metrics: Dict[str, float]) -> None:
        if experiment_id not in self.results:
            self.results[experiment_id] = []
        
        self.results[experiment_id].append(ExperimentResult(
            experiment_id=experiment_id,
            metrics=metrics,
            status="completed"
        ))

    def get_summary(self, experiment_id: str) -> Optional[Dict[str, float]]:
        runs = self.results.get(experiment_id)
        if not runs:
            return None
        
        # Average metrics across runs
        summary = {}
        for run in runs:
            for k, v in run.metrics.items():
                summary[k] = summary.get(k, 0.0) + v
        
        for k in summary:
            summary[k] /= len(runs)
        
        return summary
