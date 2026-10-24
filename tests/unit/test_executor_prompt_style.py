from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor, StepExecutionRecord


class _DummyRouter:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="ollama", name="dummy-model")


@pytest.mark.asyncio
async def test_low_risk_uses_minimal_narration_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": "", "result": None}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ok","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="read file",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "read file"},
        goal={"domain": "core", "environment": "sandbox"},
        context={},
        record=record,
    )

    assert "Default behavior: do not narrate routine, low-risk tool calls" in captured["system_prompt"]
    assert "NARRATION MODE: minimal" in captured["system_prompt"]
    assert isinstance(record.result, dict)
    assert record.result.get("meta", {}).get("narration_mode") == "minimal"


@pytest.mark.asyncio
async def test_high_risk_uses_explain_narration_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ok","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="delete files",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "run rm -rf /tmp/foo"},
        goal={"domain": "core", "environment": "sandbox"},
        context={},
        record=record,
    )

    assert "NARRATION MODE: explain" in captured["system_prompt"]
    assert isinstance(record.result, dict)
    assert record.result.get("meta", {}).get("narration_mode") == "explain"


@pytest.mark.asyncio
async def test_forbidden_actions_are_injected_into_executor_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ok","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="edit file",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "edit file"},
        goal={"domain": "core", "environment": "sandbox"},
        context={"forbidden_actions": ["nano", "wget"]},
        record=record,
    )

    assert "FORBIDDEN ACTIONS" in captured["system_prompt"]
    assert "nano" in captured["system_prompt"]
    assert "wget" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_strict_reasons_are_injected_into_executor_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ok","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="edit file",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "edit file"},
        goal={"domain": "core", "environment": "sandbox"},
        context={"strict_reasons": ["blocked_action_repeat_high", "guardrail_tuning_summary_worsening"]},
        record=record,
    )

    assert "INTELLIGENCE STRICT REASONS" in captured["system_prompt"]
    assert "blocked_action_repeat_high" in captured["system_prompt"]
