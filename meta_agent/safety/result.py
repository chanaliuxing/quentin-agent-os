# meta_agent/safety/result.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class SafetyCheckResult:
    allow_apply: bool
    requires_human_review: bool
    reasons: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        return not self.allow_apply
