# meta_agent/self_programming/mcp_integration/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from meta_agent.tools.registry import RiskLevel


@dataclass
class ServerDescriptor:
    server_id: str
    transport: str = "stdio"
    uri: Optional[str] = None
    auth_token: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredTool:
    tool_id: str
    server: ServerDescriptor
    description: str
    signature: str
    schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    raw: Dict[str, Any] = field(default_factory=dict)
