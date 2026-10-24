from __future__ import annotations

from types import SimpleNamespace
from types import ModuleType
import sys

import pytest

from quentin.cognitive.input_preprocessor import (
    preprocess_input,
    execute_command_async,
    execute_inline_action_async,
    get_input_command_registry,
    _reset_command_registry_for_tests,
)


def test_preprocess_input_extracts_directive_and_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_PREPROCESS_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "0")
    out = preprocess_input(
        text="@research /thinking high 帮我搜 RAG 论文",
        default_domain="core",
    )
    assert out.command_name == ""
    assert out.metadata_updates.get("think_level") == "high"
    assert out.metadata_updates.get("mentions") == ["research"]
    assert out.cleaned_text == "帮我搜 RAG 论文"


def test_preprocess_input_command_short_circuit() -> None:
    _reset_command_registry_for_tests()
    out = preprocess_input(text="/status", default_domain="core")
    assert out.command_name == "status"
    assert out.cleaned_text == "/status"


def test_preprocess_input_route_by_mention_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_ROUTE_BY_MENTION", "1")
    monkeypatch.setenv("QUENTIN_INPUT_MENTION_ROUTE_MAP", "research:research,ops:maintenance")
    out = preprocess_input(text="@research find papers", default_domain="core")
    assert out.route_domain == "research"


def test_preprocess_input_directive_persist_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "0")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_PERSIST", "0")
    out = preprocess_input(text="/thinking high do task", default_domain="core")
    assert out.directives.get("thinking") == "high"
    assert "think_level" not in out.metadata_updates


def test_preprocess_input_directive_allowlist_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "0")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_ALLOWLIST", "none")
    out = preprocess_input(text="/thinking high do task", default_domain="core")
    assert out.directives == {}
    assert out.metadata_updates.get("think_level") is None
    assert out.cleaned_text == "do task"


def test_preprocess_input_directive_authz_blocks_for_shared_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ALLOW_SHARED_SESSION", "0")
    out = preprocess_input(
        text="/thinking high do task",
        default_domain="core",
        metadata={"role": "user", "session_scope": "shared"},
    )
    assert out.directives == {}
    assert "think_level" not in out.metadata_updates
    assert out.metadata_updates.get("directive_authz_blocked") == ["thinking"]


def test_preprocess_input_model_and_tool_directives(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "0")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_ALLOWLIST", "thinking,model,tool")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_MODEL_ALLOWLIST", "qwen3,codex")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_TOOL_ALLOWLIST", "safe,code")
    out = preprocess_input(
        text="/model codex /tool code 请修复",
        default_domain="core",
    )
    assert out.directives.get("model") == "codex"
    assert out.directives.get("tool") == "code"
    assert out.metadata_updates.get("model_override") == "codex"
    assert out.metadata_updates.get("tool_profile") == "code"
    assert out.cleaned_text == "请修复"


def test_preprocess_input_model_directive_authz_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_ALLOWLIST", "model")
    monkeypatch.setenv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ROLES", "owner")
    out = preprocess_input(
        text="/model codex run task",
        default_domain="core",
        metadata={"role": "user", "session_scope": "private"},
    )
    assert out.directives == {}
    blocked = out.metadata_updates.get("directive_authz_blocked") or []
    assert "model" in blocked


@pytest.mark.asyncio
async def test_execute_command_async_status() -> None:
    _reset_command_registry_for_tests()
    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1", "think_level": "low"})
    parsed = preprocess_input(text="/status", default_domain="core")
    res = await execute_command_async(loop=SimpleNamespace(system_event_queue=None), task=task, parsed=parsed)
    assert isinstance(res, dict)
    assert res.get("status") == "ok"
    assert "session_id" in str(res.get("final_output") or "")


@pytest.mark.asyncio
async def test_execute_command_async_reset() -> None:
    _reset_command_registry_for_tests()
    class _Q:
        def consume_pending(self, session_id: str):  # type: ignore[no-untyped-def]
            _ = session_id
            return []

    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1", "think_level": "high", "mentions": ["research"]})
    parsed = preprocess_input(text="/reset", default_domain="core")
    res = await execute_command_async(loop=SimpleNamespace(system_event_queue=_Q()), task=task, parsed=parsed)
    assert isinstance(res, dict)
    assert task.metadata.get("think_level") == "off"
    assert "mentions" not in task.metadata


@pytest.mark.asyncio
async def test_execute_command_async_custom_registry_command(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    reg = get_input_command_registry()

    async def _echo(ctx):  # type: ignore[no-untyped-def]
        return {"status": "ok", "final_output": f"echo:{ctx.parsed.command_args}", "actions_summary": "command:/echo"}

    reg.register("echo", _echo)
    monkeypatch.setenv("QUENTIN_INPUT_COMMAND_ALLOWLIST", "status,reset,echo")

    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1"})
    parsed = preprocess_input(text="/echo hello", default_domain="core")
    res = await execute_command_async(loop=SimpleNamespace(system_event_queue=None), task=task, parsed=parsed)
    assert isinstance(res, dict)
    assert res.get("final_output") == "echo:hello"


@pytest.mark.asyncio
async def test_command_plugin_hot_plug_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    module_name = "tests.fake_command_plugin"
    plugin_mod = ModuleType(module_name)

    def register_commands(registry):  # type: ignore[no-untyped-def]
        async def _ping(ctx):  # type: ignore[no-untyped-def]
            return {"status": "ok", "final_output": f"pong:{ctx.session_id}", "actions_summary": "command:/ping"}

        registry.register("ping", _ping)

    plugin_mod.register_commands = register_commands  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, plugin_mod)
    monkeypatch.setenv("QUENTIN_INPUT_COMMAND_HANDLERS", f"{module_name}:register_commands")
    monkeypatch.setenv("QUENTIN_INPUT_COMMAND_ALLOWLIST", "ping,status,reset")

    parsed = preprocess_input(text="/ping", default_domain="core")
    assert parsed.command_name == "ping"

    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1"})
    res = await execute_command_async(loop=SimpleNamespace(system_event_queue=None), task=task, parsed=parsed)
    assert isinstance(res, dict)
    assert res.get("final_output") == "pong:s1"


def test_preprocess_input_inline_action_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_INLINE_ACTIONS_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_INPUT_INLINE_ACTION_TOOL_ALLOWLIST", "fs.exists")
    out = preprocess_input(text='/tool fs.exists {"path":"README.md"}', default_domain="core")
    assert out.command_name == ""
    assert out.inline_action.get("kind") == "tool_call"
    assert out.inline_action.get("tool_name") == "fs.exists"
    assert out.inline_action.get("arguments", {}).get("path") == "README.md"


@pytest.mark.asyncio
async def test_execute_inline_action_async_success() -> None:
    _reset_command_registry_for_tests()

    class _Res:
        success = True
        output = {"exists": True}
        error = ""

    class _TM:
        async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
            _ = (ctx,)
            assert req.tool_name == "fs.exists"
            return _Res()

    loop = SimpleNamespace(executor=SimpleNamespace(tool_manager=_TM()))
    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1"})
    parsed = preprocess_input(text='/tool fs.exists {"path":"README.md"}', default_domain="core")
    out = await execute_inline_action_async(loop=loop, task=task, parsed=parsed)
    assert isinstance(out, dict)
    assert out.get("status") == "ok"
    assert "inline_action:tool_call:fs.exists" in str(out.get("actions_summary") or "")


@pytest.mark.asyncio
async def test_execute_inline_action_async_shell_allowlist_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_command_registry_for_tests()
    monkeypatch.setenv("QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST", "pwd,ls")

    class _TM:
        async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
            _ = (req, ctx)
            raise AssertionError("should not call tool manager when shell command not allowlisted")

    loop = SimpleNamespace(executor=SimpleNamespace(tool_manager=_TM()))
    task = SimpleNamespace(task_id="t1", domain="core", environment="sandbox", metadata={"session_id": "s1"})
    parsed = preprocess_input(text='/tool shell.run_command {"command":"rm -rf /tmp/x"}', default_domain="core")
    out = await execute_inline_action_async(loop=loop, task=task, parsed=parsed)
    assert isinstance(out, dict)
    assert out.get("status") == "fallback"
    assert "not allowlisted" in str(out.get("final_output") or "")
