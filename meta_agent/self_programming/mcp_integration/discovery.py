# meta_agent/self_programming/mcp_integration/discovery.py
from __future__ import annotations
from typing import Callable, Dict, List, Sequence

from meta_agent.memory.tool_knowledge import TOOL_KNOWLEDGE_KIND
from meta_agent.memory.types import MemoryRecord
from meta_agent.self_programming.mcp_integration.client import MCPClient
from meta_agent.self_programming.mcp_integration.types import DiscoveredTool, ServerDescriptor
from meta_agent.self_programming.mcp_integration.schema_utils import synthesize_examples_from_schema
from meta_agent.tools.registry import RiskLevel
import json
from typing import Dict, Any

MemoryLoader = Callable[[], Sequence[MemoryRecord]]


class ToolDiscovery:
    """
    Discovers candidate MCP tools from registry metadata and TOOL_KNOWLEDGE memory.
    """

    def __init__(self, client: MCPClient, memory_loader: MemoryLoader | None = None) -> None:
        self.client = client
        self.memory_loader = memory_loader

    def discover_from_registry(self) -> List[DiscoveredTool]:
        candidates: List[DiscoveredTool] = []
        for server in self.client.list_registered_servers():
            for tool in self.client.list_tools(server):
                # Auto-generate examples from schema if missing and schema is present
                if not tool.examples and tool.schema:
                    tool.examples = synthesize_examples_from_schema(tool.schema)
                # Else, auto-generate a simple example from signature if missing and signature is present
                elif not tool.examples and tool.signature:
                    tool.examples = [{"input": {"_signature": tool.signature}, "usage_note": "auto-generated placeholder"}]
                candidates.append(tool)
        return candidates

    def discover_from_memory(self) -> List[DiscoveredTool]:
        if not self.memory_loader:
            return []
        candidates: List[DiscoveredTool] = []
        for record in self.memory_loader():
            if record.kind != TOOL_KNOWLEDGE_KIND:
                continue
            metadata: Dict = record.metadata or {}
            tool_id = metadata.get("tool_id")
            signature = metadata.get("signature", tool_id or "")
            server_id = metadata.get("server", "unknown-server")
            if not tool_id:
                continue
            server = ServerDescriptor(server_id=server_id, transport=metadata.get("transport", "stdio"))
            governance = metadata.get("governance", {})
            risk = governance.get("risk_level", RiskLevel.MEDIUM)
            if isinstance(risk, str):
                try:
                    risk = RiskLevel(risk)
                except ValueError:
                    risk = RiskLevel.MEDIUM
            candidates.append(
                DiscoveredTool(
                    tool_id=tool_id,
                    server=server,
                    description=metadata.get("description", record.text),
                    signature=signature,
                    schema=metadata.get("schema", {}),
                    examples=metadata.get("examples", []),
                    risk_level=risk,
                    raw=metadata,
                )
            )
        return candidates

    def discover_all(self) -> List[DiscoveredTool]:
        seen = set()
        results: List[DiscoveredTool] = []
        for tool in self.discover_from_memory() + self.discover_from_registry():
            if tool.tool_id in seen:
                continue
            seen.add(tool.tool_id)
            results.append(tool)
        return results
