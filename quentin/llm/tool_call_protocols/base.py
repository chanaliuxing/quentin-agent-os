from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable
import logging
import os

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ProtocolDecision:
    """
    Normalized decision from a tool-call protocol.
    """
    kind: str  # "tool_call" | "final" | "error"
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # [{"tool_name": "...", "args": {...}}]
    content: Optional[str] = None
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class ToolCallProtocol(Protocol):
    """
    Interface for tool call protocols (P1-D).
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def supports(self, provider: str, model_name: str, config: Any) -> bool: ...

    async def next_action(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        config: Any,
        context: Dict[str, Any],
    ) -> ProtocolDecision: ...


class ToolCallProtocolRegistry:
    """
    Registry for pluggable tool call protocols.
    """
    def __init__(self) -> None:
        self._protocols: Dict[str, ToolCallProtocol] = {}

    def register(self, protocol: ToolCallProtocol) -> None:
        self._protocols[protocol.id] = protocol

    def list_protocols(self) -> List[ToolCallProtocol]:
        return sorted(self._protocols.values(), key=lambda p: -p.priority)

    def select(self, provider: str, model_name: str, config: Any) -> Optional[ToolCallProtocol]:
        for p in self.list_protocols():
            if p.supports(provider, model_name, config):
                return p
        return None

# Global registry instance
_registry = ToolCallProtocolRegistry()

def get_tool_call_protocol_registry() -> ToolCallProtocolRegistry:
    return _registry

def _bool_env(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

def is_protocol_registry_enabled() -> bool:
    return _bool_env("QUENTIN_TOOL_CALL_PROTOCOLS", "0")
