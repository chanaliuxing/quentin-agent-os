from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from dataclasses import asdict # Required for asdict
from quentin.utils.time import now_utc_iso

@dataclass
class GoalSpec:
    goal_id: str
    title: str
    description: str
    domain: str
    environment: str
    success_criteria: List[str] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    soft_preferences: List[str] = field(default_factory=list)
    created_by: str = "agent"
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
