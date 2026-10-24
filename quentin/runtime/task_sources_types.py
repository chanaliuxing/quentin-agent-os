from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass(frozen=True)
class TaskSourceRunReport:
    """
    Legacy single-source run report (kept for back-compat with existing tests).
    """
    enqueued: int
    skipped: int
    details: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {"enqueued": int(self.enqueued), "skipped": int(self.skipped), "details": list(self.details)}
