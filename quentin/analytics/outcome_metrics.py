from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class OutcomeMetrics:
    """
    P11-D: Outcome Metrics Model
    Separates system activity from business value.
    """
    domain: str
    activity_count: int # total tasks/calls
    success_rate: float
    time_saved_hours: float
    cost_reduction_usd: float
    risk_suppression_count: int
