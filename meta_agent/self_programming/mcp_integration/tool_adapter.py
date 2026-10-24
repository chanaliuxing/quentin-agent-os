# meta_agent/self_programming/mcp_integration/tool_adapter.py
from __future__ import annotations
from typing import Iterable, List

from meta_agent.self_programming.mcp_integration.types import DiscoveredTool
from meta_agent.tools.registry import RiskLevel, ToolGovernance, ToolLifecycle, ToolRegistration, ToolRegistry


class ToolAdapter:
    """
    Converts MCP-discovered tools into the local registry format understood by
    Planner/Executor.
    """

    def __init__(self, registry: ToolRegistry, default_lifecycle: ToolLifecycle = ToolLifecycle.EXPERIMENTAL) -> None:
        self.registry = registry
        self.default_lifecycle = default_lifecycle

    def to_registration(self, tool: DiscoveredTool) -> ToolRegistration:
        lifecycle_str = tool.raw.get("governance", {}).get("lifecycle")
        lifecycle = ToolLifecycle(lifecycle_str) if lifecycle_str else self.default_lifecycle
        governance = ToolGovernance(
            lifecycle=lifecycle,
            risk_level=RiskLevel(tool.risk_level),
            domain_scope=[],
            council_score=None,
        )
        signature = tool.signature or tool.tool_id
        return ToolRegistration(
            tool_id=tool.tool_id,
            server=tool.server.server_id,
            transport=tool.server.transport,
            uri=tool.server.uri,
            description=tool.description,
            signature=signature,
            examples=tool.examples,
            auth_token=tool.server.auth_token, # Add auth_token here
            governance=governance,
        )

    def register_discovered(self, tools: Iterable[DiscoveredTool]) -> List[ToolRegistration]:
        registered: List[ToolRegistration] = []
        for tool in tools:
            reg = self.to_registration(tool)
            self.registry.register(reg)
            registered.append(reg)
        return registered
