from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import uuid

@dataclass
class ChangeRequest:
    """
    P11-C: Change Request Model
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    scope: str = "" # e.g., "global", "domain:web"
    risk_level: str = "medium"
    rollout_plan: str = ""
    rollback_plan: str = ""
    status: str = "proposed" # "proposed", "analyzing", "approved", "rolling_out", "completed", "rolled_back"
    approvals: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
