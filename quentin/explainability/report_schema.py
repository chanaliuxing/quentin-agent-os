from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any
import json

@dataclass
class AuditReport:
    report_id: str
    period_start: str
    period_end: str
    total_events: int
    risk_summary: Dict[str, int]
    violations: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        # Use a helper to serialize dataclass to dict
        from dataclasses import asdict
        return json.dumps(asdict(self), indent=2)
