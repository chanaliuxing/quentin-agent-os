# MCP Tool Learning & Integration Layer
from meta_agent.self_programming.mcp_integration.client import MCPClient
from meta_agent.self_programming.mcp_integration.discovery import ToolDiscovery
from meta_agent.self_programming.mcp_integration.tool_adapter import ToolAdapter
from meta_agent.self_programming.mcp_integration.invoker import MCPToolInvoker, ToolInvocationResult
from meta_agent.self_programming.mcp_integration.types import DiscoveredTool, ServerDescriptor

__all__ = [
    "DiscoveredTool",
    "MCPClient",
    "MCPToolInvoker",
    "ServerDescriptor",
    "ToolAdapter",
    "ToolDiscovery",
    "ToolInvocationResult",
]
