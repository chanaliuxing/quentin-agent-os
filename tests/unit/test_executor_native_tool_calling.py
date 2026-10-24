from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor, StepExecutionRecord


class _DummyToolManager:
    def __init__(self) -> None:
        self.calls = []

    async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
        self.calls.append((req, ctx))
        return {"status": "ok", "result": "tool_done"}


class _RouterOllama:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="ollama", name="qwen3-vl:latest")


class _RouterRemote:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="openai", name="gpt-4o-mini")


@pytest.mark.asyncio
async def test_executor_uses_native_tool_calling_with_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_mgr = _DummyToolManager()
    executor = Executor(model_router=_RouterOllama(), tool_manager=tool_mgr)
    record = StepExecutionRecord(
        step_id="s1",
        description="edit file",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )

    calls = {"n": 0}

    def _fake_call_llm_with_tools(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "fs.read_file",
                            "arguments": {"path": "quentin/tools/manager.py"},
                        }
                    }
                ],
            }
        return {"content": '{"status":"ok","result":"native_done"}', "tool_calls": []}

    def _should_not_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("JSON fallback path should not be used in native tool mode")

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm_with_tools", _fake_call_llm_with_tools)
    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _should_not_call_llm)

    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "edit file"},
        goal={"domain": "core", "environment": "sandbox"},
        context={"native_tool_calling": True},
        record=record,
    )

    assert calls["n"] >= 2
    assert len(tool_mgr.calls) == 1
    assert record.success is True
    assert isinstance(record.result, dict)
    assert record.result.get("meta", {}).get("tool_call_mode") == "native"


@pytest.mark.asyncio
async def test_executor_prefers_native_tool_calls_over_json_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    await test_executor_uses_native_tool_calling_with_ollama(monkeypatch)


@pytest.mark.asyncio
async def test_executor_falls_back_to_json_mode_for_non_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="do work",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        return '{"status":"ok","result":"json_mode","call_tool":null}'

    def _should_not_call_native(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("native tools should not be used for non-ollama provider")

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    monkeypatch.setattr("quentin.execution.skill_executor.call_llm_with_tools", _should_not_call_native)

    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "do work"},
        goal={"domain": "core", "environment": "sandbox"},
        context={},
        record=record,
    )

    assert record.success is True
    assert isinstance(record.result, dict)
    assert record.result.get("result") == "json_mode"


@pytest.mark.asyncio
async def test_executor_falls_back_to_json_mode_when_provider_no_native_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    await test_executor_falls_back_to_json_mode_for_non_ollama(monkeypatch)


def test_executor_strip_thinking_tags_extracts_final_payload() -> None:
    text = '<think>analysis</think><final>{"status":"ok","result":"json_mode","call_tool":null}</final>'
    stripped = Executor._strip_thinking_tags(text)
    assert stripped == '{"status":"ok","result":"json_mode","call_tool":null}'


class _GuardedToolManager:
    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
        _ = (req, ctx)
        self.calls += 1
        raise PermissionError("safety_kernel denied tool_call")


@pytest.mark.asyncio
async def test_native_tool_call_path_preserves_safety_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_mgr = _GuardedToolManager()
    executor = Executor(model_router=_RouterOllama(), tool_manager=tool_mgr)
    record = StepExecutionRecord(
        step_id="s1",
        description="dangerous action",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )

    state = {"native": 0, "json": 0}

    def _fake_call_llm_with_tools(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["native"] += 1
        return {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "shell.run_command",
                        "arguments": {"command": "rm -rf /tmp/x"},
                    }
                }
            ],
        }

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["json"] += 1
        return '{"status":"error","error":"safety_kernel denied tool_call","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm_with_tools", _fake_call_llm_with_tools)
    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "dangerous action"},
        goal={"domain": "core", "environment": "sandbox"},
        context={"native_tool_calling": True},
        record=record,
    )

    assert tool_mgr.calls >= 1
    assert state["native"] >= 1
    assert state["json"] >= 1
    assert record.success is False
    assert "safety_kernel denied tool_call" in str((record.result or {}).get("error") or "")


@pytest.mark.asyncio
async def test_executor_incremental_json_feedback_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_mgr = _DummyToolManager()
    executor = Executor(model_router=_RouterRemote(), tool_manager=tool_mgr)
    record = StepExecutionRecord(
        step_id="s1",
        description="update file",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    state = {"n": 0}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["n"] += 1
        if state["n"] == 1:
            return '{"status":"ok","result":"step1","call_tool":{"tool_name":"fs.read_file","args":{"path":"x.py"}}}'
        return '{"status":"ok","result":"final_done","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "update file"},
        goal={"domain": "core", "environment": "sandbox"},
        context={"max_step_iterations": 4, "native_tool_calling": False},
        record=record,
    )

    assert state["n"] == 2
    assert len(tool_mgr.calls) == 1
    assert record.success is True
    assert record.result.get("meta", {}).get("iterations") == 2


def test_executor_strategy_guard_for_complex_coding_step() -> None:
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    should_block = executor._should_enforce_coding_tool(
        desc="Use gemini.code to implement complex html parser logic for 小红书",
        tool_call={"tool_name": "fs.write_file", "args": {"path": "x.py", "content": "x"}},
    )
    assert should_block is True


def test_executor_dead_loop_diagnostic_probes_shape() -> None:
    probes = Executor._dead_loop_diagnostic_probes()
    names = [p.get("tool_name") for p in probes if isinstance(p, dict)]
    assert "pwd" in names
    assert "shell.run_command" in names
    assert "ls" in names
    assert "fs.get_write_policy" in names


def test_executor_strategy_guard_allows_env_fallback_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUENTIN_CODING_TOOL_ALLOW_DIRECT_WRITE_FALLBACK", "1")
    monkeypatch.setenv("QUENTIN_CODING_TOOL_FALLBACK_AFTER_ITER", "2")
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    should_block_first = executor._should_enforce_coding_tool(
        desc="complex html parser refactor",
        tool_call={"tool_name": "fs.write_file", "args": {"path": "x.py", "content": "x"}},
        iteration=1,
    )
    should_block_second = executor._should_enforce_coding_tool(
        desc="complex html parser refactor",
        tool_call={"tool_name": "fs.write_file", "args": {"path": "x.py", "content": "x"}},
        iteration=2,
    )
    assert should_block_first is True
    assert should_block_second is False


def test_executor_strategy_guard_can_be_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUENTIN_CODING_TOOL_GUARD_ENABLED", "0")
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    should_block = executor._should_enforce_coding_tool(
        desc="complex html parser refactor",
        tool_call={"tool_name": "fs.write_file", "args": {"path": "x.py", "content": "x"}},
        iteration=1,
    )
    assert should_block is False


def test_executor_normalize_json_tool_call_accepts_name_arguments_variant() -> None:
    tc = Executor._normalize_json_tool_call(
        {"name": "shell.run_command", "arguments": {"command": "pwd"}}
    )
    assert tc == {"tool_name": "shell.run_command", "args": {"command": "pwd"}}


def test_executor_normalize_json_tool_call_synthesizes_top_level_write_args() -> None:
    tc = Executor._normalize_json_tool_call(
        {"tool_id": "fs_write_file", "path": "generated/out.txt", "content": "OK", "mode": "overwrite"}
    )
    assert tc == {
        "tool_name": "fs.write_file",
        "args": {"path": "generated/out.txt", "content": "OK", "mode": "overwrite"},
    }
