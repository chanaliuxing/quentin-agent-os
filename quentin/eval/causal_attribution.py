from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class CausalEvidence:
    change_id: str
    metric_impacted: str
    impact_magnitude: float
    evidence_chain: List[str]

class CausalAttributionStore:
    """
    P8-C: Causal Attribution
    Links changes to metric movements to avoid noise-driven learning.
    """
    def __init__(self) -> None:
        self.evidence: List[CausalEvidence] = []

    def record_impact(self, change_id: str, metric: str, magnitude: float, logic: List[str]) -> None:
        self.evidence.append(CausalEvidence(change_id, metric, magnitude, logic))

    def get_top_contributors(self, metric: str) -> List[CausalEvidence]:
        return sorted([e for e in self.evidence if e.metric_impacted == metric], key=lambda x: abs(x.impact_magnitude), reverse=True)
