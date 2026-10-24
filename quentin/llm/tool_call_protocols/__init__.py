from __future__ import annotations

from quentin.llm.tool_call_protocols.base import (
    ToolCallProtocol,
    ToolCallProtocolRegistry,
    ProtocolDecision,
    get_tool_call_protocol_registry,
    is_protocol_registry_enabled,
)
from quentin.llm.tool_call_protocols.native_tools_protocol import NativeToolsProtocol
from quentin.llm.tool_call_protocols.json_fallback_protocol import JsonFallbackProtocol
from quentin.llm.tool_call_protocols.noop_protocol import NoopProtocol

def bootstrap_protocols(registry: ToolCallProtocolRegistry = None) -> ToolCallProtocolRegistry:
    if registry is None:
        registry = get_tool_call_protocol_registry()
    
    registry.register(NativeToolsProtocol())
    registry.register(JsonFallbackProtocol())
    registry.register(NoopProtocol())
    
    return registry

__all__ = [
    "ToolCallProtocol",
    "ToolCallProtocolRegistry",
    "ProtocolDecision",
    "get_tool_call_protocol_registry",
    "is_protocol_registry_enabled",
    "bootstrap_protocols",
]
