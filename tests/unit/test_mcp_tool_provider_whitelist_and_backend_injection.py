from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.tools.manager import ToolManager
from quentin.tools.providers.mcp import MCPToolProvider


@dataclass
class _StubInvokeResult:
    success: bool
    output: Any
    error: Optional[str]
    latency_ms: int


class _StubInvoker:
    def invoke(self, *, server: Any, tool_name: str, arguments: Dict[str, Any]) -> _StubInvokeResult:
        _ = (server, tool_name, arguments)
        return _StubInvokeResult(success=True, output={"ok": True}, error=None, latency_ms=1)


@dataclass
class _StubServerDescriptor:
    server_id: str
    transport: str
    uri: Optional[str]
    auth_token: Optional[str]
    metadata: Dict[str, Any]


def test_mcp_provider_enabled_but_no_whitelist_registers_none(tmp_path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "mcp_security.yaml").write_text(
        "\n".join(
            [
                "mcp_security:",
                "  enabled: true",
                "  allow_auto_tool_install: false",
                "  whitelist: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "mcp_registry.json").write_text("[]\n", encoding="utf-8")

    tm = ToolManager()
    report = MCPToolProvider().register(tool_manager=tm, repo_root=str(tmp_path))
    assert report.enabled is True
    assert report.registered_tools == []
    assert report.errors == []


def test_mcp_provider_whitelist_allows_registration_with_stub_backend(tmp_path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "mcp_security.yaml").write_text(
        "\n".join(
            [
                "mcp_security:",
                "  enabled: true",
                "  allow_auto_tool_install: false",
                "  enable_tool_learning: true",
                "  tool_learning_max_examples: 1",
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
                {
                    "name": "demo_tool",
                    "description": "d",
                    "signature": "demo_tool(x)",
                    "risk_level": "low",
                    "schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            ],
        }
    ]
    (tmp_path / "config" / "mcp_registry.json").write_text(json.dumps(registry), encoding="utf-8")

    tm = ToolManager()

    def _backend_loader():
        return _StubInvoker(), _StubServerDescriptor

    report = MCPToolProvider(backend_loader=_backend_loader).register(tool_manager=tm, repo_root=str(tmp_path))
    assert report.enabled is True
    assert "mcp.demo_server.demo_tool" in report.registered_tools

    spec = getattr(tm, "_specs", {}).get("mcp.demo_server.demo_tool")
    assert spec is not None
    meta = getattr(spec, "meta", {}) or {}
    assert isinstance(meta.get("examples"), list) and meta["examples"]
