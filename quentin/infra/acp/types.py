from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class ACPMethod(str, Enum):
    NODE_PAIR = "node.pair"
    NODE_REGISTER = "node.register"
    NODE_INVOKE = "node.invoke"
    NODE_EVENT = "node.event"
    SERVER_HEARTBEAT = "server.heartbeat"

@dataclass
class ACPRequest:
    jsonrpc: str = "2.0"
    id: str = field(default_factory=lambda: "req_default")
    method: ACPMethod = ACPMethod.NODE_INVOKE
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method.value,
            "params": self.params
        }

@dataclass
class ACPResponse:
    jsonrpc: str = "2.0"
    id: str = ""
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ACPResponse:
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id", ""),
            result=data.get("result"),
            error=data.get("error")
        )
