from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor


class _RouterRemote:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="openai", name="gpt-4o-mini")


@pytest.mark.asyncio
async def test_executor_step_feedback_updates_next_action(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"n": 0}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["n"] += 1
        user_prompt = str(kwargs.get("user_prompt") or "")
        if state["n"] == 1:
            assert '"feedback": []' in user_prompt
            return '{"status":"ok","result":"first","call_tool":{"tool_name":"fs.read_file","args":{"path":"x.py"}}}'
        assert "tool_result" in user_prompt
        return '{"status":"ok","result":"final update complete","call_tool":null}'

    class _ToolMgr:
        async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
            _ = (req, ctx)
            return {"status": "ok", "result": "content"}

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_RouterRemote(), tool_manager=_ToolMgr())
    out = await executor.execute_plan(
        goal={"domain": "core", "environment": "sandbox"},
        plan={"steps": [{"step_id": "s1", "description": "do task"}]},
        context={"max_step_iterations": 4, "native_tool_calling": False},
    )
    assert out["success"] is True
    step = out["steps"][0]
    assert (step.get("result") or {}).get("meta", {}).get("iterations") == 2
    assert state["n"] == 2


@pytest.mark.asyncio
async def test_executor_breaks_on_no_progress_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","result":"","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    out = await executor.execute_plan(
        goal={"domain": "core", "environment": "sandbox"},
        plan={"steps": [{"step_id": "s1", "description": "do task"}]},
        context={"max_step_iterations": 5, "no_progress_threshold": 2, "native_tool_calling": False},
    )
    assert out["success"] is False
    step = out["steps"][0]
    result = step.get("result") or {}
    assert result.get("error") == "no_progress_threshold_reached"
    assert int((result.get("meta") or {}).get("no_progress_streak") or 0) >= 2


@pytest.mark.asyncio
async def test_incremental_loop_resumes_from_failed_step_not_from_step1(monkeypatch: pytest.MonkeyPatch) -> None:
    touched = []

    async def _fake_execute_step(self, *, step, goal, context):  # type: ignore[no-untyped-def]
        _ = (goal, context)
        touched.append(str(step.get("step_id")))
        from quentin.execution.skill_executor import StepExecutionRecord

        return StepExecutionRecord(
            step_id=str(step.get("step_id")),
            description=str(step.get("description") or ""),
            skill_id=None,
            executor_mode="llm",
            success=True,
            result={"status": "ok", "result": "done"},
        )

    monkeypatch.setattr("quentin.execution.skill_executor.Executor._execute_step", _fake_execute_step)
    executor = Executor(model_router=_RouterRemote(), tool_manager=None)
    out = await executor.execute_plan(
        goal={"domain": "core", "environment": "sandbox"},
        plan={
            "steps": [
                {"step_id": "s1", "description": "first"},
                {"step_id": "s2", "description": "second"},
                {"step_id": "s3", "description": "third"},
            ]
        },
        context={"resume_from_step_index": 1},
    )
    assert out["success"] is True
    assert touched == ["s2", "s3"]
    assert (out.get("meta") or {}).get("resume_from_step_index") == 1


@pytest.mark.asyncio
async def test_repeated_read_only_tool_calls_have_higher_loop_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"n": 0}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        state["n"] += 1
        if state["n"] <= 3:
            return '{"status":"ok","result":"","call_tool":{"tool_name":"ls","args":{"path":"."}}}'
        return '{"status":"ok","result":"done","call_tool":null}'

    class _ToolMgr:
        async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
            _ = (req, ctx)
            return {"status": "ok", "result": "listing"}

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_RouterRemote(), tool_manager=_ToolMgr())
    out = await executor.execute_plan(
        goal={"domain": "core", "environment": "sandbox"},
        plan={"steps": [{"step_id": "s1", "description": "inspect then finish"}]},
        context={"max_step_iterations": 6, "native_tool_calling": False},
    )
    assert out["success"] is True
    assert state["n"] == 4


@pytest.mark.asyncio
async def test_repeated_mutating_tool_calls_still_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","result":"","call_tool":{"tool_name":"fs.write_file","args":{"path":"generated/a.md","content":"x"}}}'

    class _ToolMgr:
        async def call_tool(self, req, ctx):  # type: ignore[no-untyped-def]
            _ = (req, ctx)
            return {"status": "ok", "result": "written"}

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)
    executor = Executor(model_router=_RouterRemote(), tool_manager=_ToolMgr())
    out = await executor.execute_plan(
        goal={"domain": "core", "environment": "sandbox"},
        plan={"steps": [{"step_id": "s1", "description": "write file"}]},
        context={"max_step_iterations": 6, "native_tool_calling": False},
    )
    assert out["success"] is False
    step = out["steps"][0]
    result = step.get("result") or {}
    assert result.get("error") == "repeated_tool_call_loop"
    assert int((result.get("meta") or {}).get("repeat_limit") or 0) == 3
