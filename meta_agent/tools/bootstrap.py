# meta_agent/tools/bootstrap.py
from __future__ import annotations
from typing import Any, Callable, Iterable, List, Sequence

from meta_agent.memory.tool_knowledge import TOOL_KNOWLEDGE_KIND
from meta_agent.memory.types import MemoryRecord, MemoryTier
from meta_agent.self_programming.mcp_integration import (
    DiscoveredTool,
    MCPClient,
    ToolAdapter,
    ToolDiscovery,
)
from meta_agent.tools.registry import ToolLifecycle, ToolRegistration, ToolRegistry


def _default_memory_loader(memory_search: Callable[..., Sequence[MemoryRecord]]) -> Callable[[], Sequence[MemoryRecord]]:
    def load() -> Sequence[MemoryRecord]:
        return memory_search("", tiers=[MemoryTier.LTS], kind=TOOL_KNOWLEDGE_KIND, limit=200)

    return load


def bootstrap_registry(
    *,
    registry_index: Iterable[dict[str, Any]] | None = None,
    memory_search: Callable[..., Sequence[MemoryRecord]] | None = None,
    default_lifecycle: ToolLifecycle = ToolLifecycle.EXPERIMENTAL,
) -> ToolRegistry:
    """
    Build a ToolRegistry by combining:
    - registry metadata (MCP servers + tools)
    - TOOL_KNOWLEDGE memory entries (if provided via memory_search)

    This keeps Planner/Executor consumers decoupled from MCP transport details.
    """
    registry = ToolRegistry()
    client = MCPClient(registry_index=registry_index)
    memory_loader = _default_memory_loader(memory_search) if memory_search else None
    discovery = ToolDiscovery(client=client, memory_loader=memory_loader)
    adapter = ToolAdapter(registry=registry, default_lifecycle=default_lifecycle)

    discovered: List[DiscoveredTool] = discovery.discover_all()
    adapter.register_discovered(discovered)

    return registry
