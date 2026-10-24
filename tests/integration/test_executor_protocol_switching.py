from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor, StepExecutionRecord


class _StubRouter:
    def route(self, mode, task_type):  # type: ignore[no-untyped-def]
        _ = (mode, task_type)
        return SimpleNamespace(provider="ollama", name="qwen2.5:7b")


@pytest.mark.asyncio
async def test_executor_protocol_switches_native_to_json_fallback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUENTIN_TOOL_CALL_PROTOCOLS", "1")
    monkeypatch.setenv("QUENTIN_EXECUTOR_NATIVE_TOOL_CALLING", "1")

    def _native_fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        raise RuntimeError("native tools unavailable")

    def _json_success(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","result":"done via fallback"}'

    monkeypatch.setattr("quentin.llm.tool_call_protocols.native_tools_protocol.call_llm_with_tools", _native_fail)
    monkeypatch.setattr("quentin.llm.tool_call_protocols.json_fallback_protocol.call_llm", _json_success)
    monkeypatch.setattr("quentin.llm.tool_call_protocols.noop_protocol.call_llm", _json_success)

    ex = Executor(repo_root=tmp_path, model_router=_StubRouter(), skill_manager=SimpleNamespace(match_skill=lambda *a, **k: None))
    rec = StepExecutionRecord(
        step_id="s1",
        description="d",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    goal = SimpleNamespace(domain="core", environment="sandbox")
    await ex._fallback_llm_execute(step={"step_id": "s1", "description": "d"}, goal=goal, context={}, record=rec)

    assert isinstance(rec.result, dict)
    meta = rec.result.get("meta") if isinstance(rec.result, dict) else {}
    assert isinstance(meta, dict)
    assert meta.get("protocol") == "json_fallback"
    chain = meta.get("protocol_chain") if isinstance(meta, dict) else None
    assert isinstance(chain, list)
    assert chain[:2] == ["native_tools", "json_fallback"]
