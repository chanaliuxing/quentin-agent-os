from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
import uuid

@dataclass
class FederationEnvelope:
    """
    P7-A: Federation Message Protocol
    """
    trace_id: str
    source_node: str
    target_node: str
    payload: Dict[str, Any]
    message_type: str # "task", "sync", "heartbeat"
    signature: str = ""
    timestamp: float = field(default_factory=lambda: time.time())
    ttl: int = 60 # seconds

    @classmethod
    def new(cls, source: str, target: str, type: str, payload: Dict[str, Any]) -> FederationEnvelope:
        return cls(
            trace_id=uuid.uuid4().hex,
            source_node=source,
            target_node=target,
            message_type=type,
            payload=payload
        )
