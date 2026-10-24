from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class SLODefinition:
    name: str
    target: float # e.g., 0.99 for 99%
    metric_key: str
    window_days: int = 30
    description: str = ""

class SLORegistry:
    """
    P5-A: SLO Definition Center
    Maintains availability, latency, and correctness SLOs.
    """
    def __init__(self) -> None:
        self.slos: Dict[str, SLODefinition] = {}
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        self.register(SLODefinition(
            name="availability",
            target=0.999,
            metric_key="system_availability",
            description="Overall system uptime and success rate"
        ))
        self.register(SLODefinition(
            name="latency_p95",
            target=2000.0, # 2s
            metric_key="avg_latency_ms",
            description="P95 latency should be under 2s"
        ))
        self.register(SLODefinition(
            name="safety_fp_rate",
            target=0.01, # 1%
            metric_key="safety_false_positive_rate",
            description="Safety block false-positive rate should be under 1%"
        ))

    def register(self, slo: SLODefinition) -> None:
        self.slos[slo.name] = slo

    def get_slo(self, name: str) -> Optional[SLODefinition]:
        return self.slos.get(name)

    def list_all(self) -> Dict[str, SLODefinition]:
        return self.slos
