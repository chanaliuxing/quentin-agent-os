from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor, StepExecutionRecord


class _DummyRouter:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="ollama", name="dummy-model")


@pytest.mark.asyncio
async def test_executor_injects_progressive_pressure_note(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"progress update","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="do work",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "do work"},
        goal={"domain": "core", "environment": "sandbox"},
        context={
            "progressive_pressure": True,
            "progressive_pressure_note": "Please provide a brief update first.",
        },
        record=record,
    )

    assert "PROGRESS PRESSURE" in captured["system_prompt"]
    assert "Please provide a brief update first." in captured["system_prompt"]
    assert "Never use interactive editors" in captured["system_prompt"]
    assert "Never use guessed download/install URLs" in captured["system_prompt"]
    assert record.success is True


@pytest.mark.asyncio
async def test_executor_injects_self_awareness_note(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ack","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

    executor = Executor(model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="do work",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    await executor._fallback_llm_execute(
        step={"step_id": "s1", "description": "do work"},
        goal={"domain": "core", "environment": "sandbox"},
        context={
            "self_awareness_note": "status=warning; failover_reason=context_overflow",
        },
        record=record,
    )

    assert "SELF AWARENESS" in captured["system_prompt"]
    assert "failover_reason=context_overflow" in captured["system_prompt"]
    assert record.success is True
