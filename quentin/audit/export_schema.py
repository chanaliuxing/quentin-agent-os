from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any
import json

@dataclass
class AuditBundle:
    bundle_id: str
    exported_at: str
    events: List[Dict[str, Any]]
    integrity_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), indent=2)
