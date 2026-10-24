from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.tools.manager import ToolManager
from quentin.tools.providers.mcp import MCPToolProvider


@dataclass
class _StubInvokeResult:
    success: bool
    output: Any
    error: Optional[str]
    latency_ms: int


class _FailingInvoker:
    def invoke(self, *, server: Any, tool_name: str, arguments: Dict[str, Any]) -> _StubInvokeResult:
        _ = (server, tool_name, arguments)
        return _StubInvokeResult(success=False, output=None, error="backend_unavailable", latency_ms=7)


@dataclass
class _StubServerDescriptor:
    server_id: str
    transport: str
    uri: Optional[str]
    auth_token: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class _Req:
    payload: Dict[str, Any]


def _write_enabled_config(tmp_path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "mcp_security.yaml").write_text(
        "\n".join(
            [
                "mcp_security:",
                "  enabled: true",
                "  allow_auto_tool_install: false",
                "  whitelist:",
                "    - demo_server/demo_tool",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    registry = [
        {
            "server_id": "demo_server",
            "transport": "stdio",
            "tools": [
                {"name": "demo_tool", "description": "d", "risk_level": "low", "schema": {"type": "object"}},
            ],
        }
    ]
    (tmp_path / "config" / "mcp_registry.json").write_text(json.dumps(registry), encoding="utf-8")


def test_mcp_provider_backend_unavailable_returns_degrade_report(tmp_path) -> None:
    _write_enabled_config(tmp_path)
    tm = ToolManager()

    def _broken_backend_loader():
        raise RuntimeError("invoker missing")

    report = MCPToolProvider(backend_loader=_broken_backend_loader).register(tool_manager=tm, repo_root=str(tmp_path))
    assert report.enabled is True
    assert report.registered_tools == []
    assert report.errors
    assert "mcp_backend_unavailable" in str(report.errors[0].get("error"))


def test_mcp_tool_handler_maps_invoker_failure_to_error_payload(tmp_path) -> None:
    _write_enabled_config(tmp_path)
    tm = ToolManager()

    def _backend_loader():
        return _FailingInvoker(), _StubServerDescriptor

    report = MCPToolProvider(backend_loader=_backend_loader).register(tool_manager=tm, repo_root=str(tmp_path))
    assert "mcp.demo_server.demo_tool" in report.registered_tools

    handler = tm.get("mcp.demo_server.demo_tool")
    out = handler(_Req(payload={"x": 1}))
    assert isinstance(out, dict)
    assert out["status"] == "error"
    assert out["error"] == "backend_unavailable"
    assert out["latency_ms"] == 7
