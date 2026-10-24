from __future__ import annotations

from quentin.tools.manager import ToolManager
from quentin.tools.providers.mcp import MCPToolProvider


def test_mcp_provider_disabled_by_default(tmp_path) -> None:
    tm = ToolManager()
    report = MCPToolProvider().register(tool_manager=tm, repo_root=str(tmp_path))
    assert report.enabled is False
    assert report.registered_tools == []

