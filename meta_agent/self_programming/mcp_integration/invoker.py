# meta_agent/self_programming/mcp_integration/invoker.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import asyncio
import time
import json

from meta_agent.self_programming.mcp_integration.types import ServerDescriptor

try:
    from mcp import AsyncClient
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _MCP_AVAILABLE = False

try:
    import websockets  # type: ignore

    _WS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _WS_AVAILABLE = False


@dataclass
class ToolInvocationResult:
    success: bool
    output: Any
    latency_ms: float
    error: Optional[str] = None


class MCPToolInvoker:
    """
    Minimal MCP invoker. Supports stdio; websocket hook is a placeholder.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def invoke(self, server: ServerDescriptor, tool_name: str, arguments: Dict[str, Any]) -> ToolInvocationResult:
        if not _MCP_AVAILABLE:
            return ToolInvocationResult(
                success=False,
                output=None,
                latency_ms=0.0,
                error="mcp package not installed",
            )
        if server.transport == "websocket":
            return self._invoke_websocket(server, tool_name, arguments)
        if server.transport != "stdio":
            return ToolInvocationResult(
                success=False,
                output=None,
                latency_ms=0.0,
                error=f"unsupported transport: {server.transport}",
            )
        if not server.uri:
            return ToolInvocationResult(
                success=False,
                output=None,
                latency_ms=0.0,
                error="server uri missing for stdio transport",
            )

        async def _run() -> ToolInvocationResult:
            started = time.perf_counter()
            try:
                async with stdio_client(server.uri, env={"MCP_AUTH_TOKEN": server.auth_token} if server.auth_token else None) as (read, write):
                    client = AsyncClient(read, write)
                    session = ClientSession(client)
                    await session.initialize()
                    resp = await asyncio.wait_for(
                        session.call_tool(tool_name, arguments),
                        timeout=self.timeout,
                    )
                    elapsed = (time.perf_counter() - started) * 1000.0
                    return ToolInvocationResult(success=True, output=resp, latency_ms=elapsed)
            except Exception as e:
                elapsed = (time.perf_counter() - started) * 1000.0
                return ToolInvocationResult(
                    success=False,
                    output=None,
                    latency_ms=elapsed,
                    error=repr(e),
                )

        return asyncio.run(_run())

    def _invoke_websocket(self, server: ServerDescriptor, tool_name: str, arguments: Dict[str, Any]) -> ToolInvocationResult:
        if not _WS_AVAILABLE:
            return ToolInvocationResult(
                success=False,
                output=None,
                latency_ms=0.0,
                error="websocket transport requested but websockets package not installed",
            )
        if not server.uri:
            return ToolInvocationResult(
                success=False,
                output=None,
                latency_ms=0.0,
                error="server uri missing for websocket transport",
            )

        async def _run() -> ToolInvocationResult:
            started = time.perf_counter()
            try:
                async with websockets.connect(server.uri, extra_headers={"Authorization": f"Bearer {server.auth_token}"} if server.auth_token else None) as ws:  # type: ignore
                    payload = json.dumps({"tool": tool_name, "arguments": arguments})
                    await asyncio.wait_for(ws.send(payload), timeout=self.timeout)
                    resp = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                    elapsed = (time.perf_counter() - started) * 1000.0
                    try:
                        parsed = json.loads(resp)
                    except Exception:
                        parsed = resp
                    return ToolInvocationResult(success=True, output=parsed, latency_ms=elapsed)
            except Exception as e:
                elapsed = (time.perf_counter() - started) * 1000.0
                return ToolInvocationResult(
                    success=False,
                    output=None,
                    latency_ms=elapsed,
                    error=repr(e),
                )

        return asyncio.run(_run())
