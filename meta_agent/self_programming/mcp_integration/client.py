# meta_agent/self_programming/mcp_integration/client.py
from __future__ import annotations
from typing import Dict, Iterable, List
import json
import urllib.request

from meta_agent.self_programming.mcp_integration.types import DiscoveredTool, ServerDescriptor
from meta_agent.tools.registry import RiskLevel


class MCPClient:
    """
    Lightweight placeholder client for MCP servers.

    Real transport (stdio / websocket) will be added later; for now we consume
    server metadata to hydrate tool descriptors so discovery + registry wiring
    can be implemented incrementally.
    """

    def __init__(self, registry_index: Iterable[Dict] | None = None) -> None:
        self.registry_index = list(registry_index or [])

    def list_registered_servers(self) -> List[ServerDescriptor]:
        servers: List[ServerDescriptor] = []
        for entry in self.registry_index:
            server = ServerDescriptor(
                server_id=entry.get("server_id") or entry.get("name", "unknown-server"),
                transport=entry.get("transport", "stdio"),
                uri=entry.get("uri"),
                auth_token=entry.get("auth_token"),
                metadata=entry,
            )
            servers.append(server)
        return servers

    @classmethod
    def from_remote(cls, url: str) -> "MCPClient":
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                payload = resp.read().decode("utf-8")
            data = json.loads(payload or "[]")
        except Exception:
            data = []
        return cls(registry_index=data)

    def list_tools(self, server: ServerDescriptor) -> List[DiscoveredTool]:
        tools_raw = server.metadata.get("tools") or []
        discovered: List[DiscoveredTool] = []
        for tool in tools_raw:
            tool_id = tool.get("name") or tool.get("tool_id")
            if not tool_id:
                continue
            discovered.append(
                DiscoveredTool(
                    tool_id=f"{server.server_id}/{tool_id}",
                    server=server,
                    description=tool.get("description", ""),
                    signature=tool.get("signature", tool_id),
                    schema=tool.get("schema", {}),
                    examples=tool.get("examples", []),
                    risk_level=RiskLevel(tool.get("risk_level", RiskLevel.MEDIUM)),
                    raw=tool,
                )
            )
        return discovered
