from dataclasses import dataclass, asdict, field
import time
import json
from typing import Any, Dict

@dataclass
class AuditEvent:
    event_id: str
    actor: str
    action: str
    resource: str
    decision: str  # allow/block
    reason: str
    trace_id: str = "unknown"
    session_id: str = "global"
    ts: float = field(default_factory=lambda: time.time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
