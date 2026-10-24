from __future__ import annotations

import asyncio

from quentin.tools.manager import ToolManager
from quentin.tools.schemas import ToolCallRequest


def test_tool_manager_lazy_reload_registers_plugins(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_LAZY_RELOAD", "true")
    monkeypatch.setenv("QUENTIN_TOOL_CACHE_PATH", str(tmp_path / "tool_cache.db"))

    plugin_dir = tmp_path / "extensions" / "tools" / "lazy_echo"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: lazy_echo",
                "name: plugin.lazy_echo",
                "description: lazy",
                "entrypoint: logic:run",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "logic.py").write_text(
        "\n".join(
            [
                "def run(payload, ctx=None):",
                "    _ = ctx",
                "    return {'status': 'ok', 'x': payload.get('x', 0)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tm = ToolManager()
    tm.set_repo_root(str(tmp_path))
    res = asyncio.run(tm.call_tool(ToolCallRequest(tool_name="plugin.lazy_echo", payload={"x": 7})))
    assert res.success is True
    assert (res.output or {}).get("result", {}).get("x") == 7
