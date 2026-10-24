from __future__ import annotations

import asyncio
import time
from pathlib import Path

from quentin.tools.manager import ToolManager
from quentin.tools.plugin_loader import register_tool_plugins
from quentin.tools.schemas import ToolCallRequest


def test_register_tool_plugins_discovers_and_executes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_TOOL_CACHE_PATH", str(tmp_path / "tool_cache.db"))

    plugin_dir = tmp_path / "extensions" / "tools" / "echo_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: echo_plugin",
                "name: plugin.echo",
                "description: Echo plugin tool",
                "entrypoint: logic:run",
                "output_trust: untrusted",
                "cache:",
                "  enabled: true",
                "  ttl_sec: 3600",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "logic.py").write_text(
        "\n".join(
            [
                "COUNTER = 0",
                "",
                "def run(payload, ctx=None):",
                "    global COUNTER",
                "    COUNTER += 1",
                "    return {'n': COUNTER, 'payload': payload}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tm = ToolManager()
    report = register_tool_plugins(tool_manager=tm, repo_root=tmp_path)
    assert report["registered"] == 1
    assert "plugin.echo" in report.get("tools", [])

    req = ToolCallRequest(tool_name="plugin.echo", payload={"x": 1})
    res1 = asyncio.run(tm.call_tool(req))
    assert res1.success is True
    assert (res1.output or {}).get("result", {}).get("n") == 1
    assert (res1.meta or {}).get("untrusted_output_wrapped") is True
    assert "_untrusted_wrapped_text" in (res1.output or {})

    # Second call should hit cache (and keep n==1 due to cached value).
    res2 = asyncio.run(tm.call_tool(req))
    assert res2.success is True
    assert (res2.output or {}).get("cached") is True
    # Cached payload stores the prior output dict.
    cached = (res2.output or {}).get("result") or {}
    assert cached.get("result", {}).get("n") == 1


def test_plugin_cache_key_fields_controls_cache_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_TOOL_CACHE_PATH", str(tmp_path / "tool_cache.db"))

    plugin_dir = tmp_path / "extensions" / "tools" / "key_fields_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: key_fields_plugin",
                "name: plugin.key_fields",
                "entrypoint: logic:run",
                "output_trust: untrusted",
                "cache:",
                "  enabled: true",
                "  ttl_sec: 3600",
                "  key_fields: [x]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "logic.py").write_text(
        "\n".join(
            [
                "COUNTER = 0",
                "",
                "def run(payload, ctx=None):",
                "    global COUNTER",
                "    COUNTER += 1",
                "    return {'n': COUNTER, 'payload': payload}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tm = ToolManager()
    report = register_tool_plugins(tool_manager=tm, repo_root=tmp_path)
    assert report["registered"] == 1

    req1 = ToolCallRequest(tool_name="plugin.key_fields", payload={"x": 1, "y": "A"})
    req2 = ToolCallRequest(tool_name="plugin.key_fields", payload={"x": 1, "y": "B"})
    req3 = ToolCallRequest(tool_name="plugin.key_fields", payload={"x": 2, "y": "B"})

    res1 = asyncio.run(tm.call_tool(req1))
    assert res1.success is True
    assert (res1.output or {}).get("result", {}).get("n") == 1

    res2 = asyncio.run(tm.call_tool(req2))
    assert res2.success is True
    assert (res2.output or {}).get("cached") is True
    assert (res2.meta or {}).get("cache_key_fields") == ["x"]

    res3 = asyncio.run(tm.call_tool(req3))
    assert res3.success is True
    assert (res3.output or {}).get("cached") is not True
    assert (res3.output or {}).get("result", {}).get("n") == 2


def test_plugin_cache_stale_while_revalidate_window(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_TOOL_CACHE_PATH", str(tmp_path / "tool_cache.db"))

    plugin_dir = tmp_path / "extensions" / "tools" / "swr_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: swr_plugin",
                "name: plugin.swr",
                "entrypoint: logic:run",
                "output_trust: untrusted",
                "cache:",
                "  enabled: true",
                "  ttl_sec: 1",
                "  stale_while_revalidate: 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "logic.py").write_text(
        "\n".join(
            [
                "COUNTER = 0",
                "",
                "def run(payload, ctx=None):",
                "    global COUNTER",
                "    COUNTER += 1",
                "    return {'n': COUNTER}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tm = ToolManager()
    register_tool_plugins(tool_manager=tm, repo_root=tmp_path)

    req = ToolCallRequest(tool_name="plugin.swr", payload={"x": 1})
    res1 = asyncio.run(tm.call_tool(req))
    assert res1.success is True
    assert (res1.output or {}).get("result", {}).get("n") == 1
    time.sleep(1.2)
    res2 = asyncio.run(tm.call_tool(req))
    assert res2.success is True
    assert (res2.output or {}).get("cached") is True
    assert (res2.output or {}).get("cache_stale") is True
    cached = (res2.output or {}).get("result") or {}
    assert cached.get("result", {}).get("n") == 1


def test_plugin_cache_max_bytes_evicts_old_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TOOL_PLUGINS_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_TOOL_CACHE_PATH", str(tmp_path / "tool_cache.db"))

    plugin_dir = tmp_path / "extensions" / "tools" / "size_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: size_plugin",
                "name: plugin.size",
                "entrypoint: logic:run",
                "output_trust: untrusted",
                "cache:",
                "  enabled: true",
                "  ttl_sec: 3600",
                "  key_fields: [x]",
                "  max_bytes: 350",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "logic.py").write_text(
        "\n".join(
            [
                "COUNTER = 0",
                "",
                "def run(payload, ctx=None):",
                "    global COUNTER",
                "    COUNTER += 1",
                "    return {'n': COUNTER, 'blob': 'z' * 120, 'x': payload.get('x')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tm = ToolManager()
    register_tool_plugins(tool_manager=tm, repo_root=tmp_path)

    req1 = ToolCallRequest(tool_name="plugin.size", payload={"x": 1})
    req2 = ToolCallRequest(tool_name="plugin.size", payload={"x": 2})

    first = asyncio.run(tm.call_tool(req1))
    assert first.success is True
    assert (first.output or {}).get("result", {}).get("n") == 1

    second = asyncio.run(tm.call_tool(req2))
    assert second.success is True
    assert (second.output or {}).get("result", {}).get("n") == 2

    again_first = asyncio.run(tm.call_tool(req1))
    assert again_first.success is True
    assert (again_first.output or {}).get("cached") is not True
    assert (again_first.output or {}).get("result", {}).get("n") == 3
