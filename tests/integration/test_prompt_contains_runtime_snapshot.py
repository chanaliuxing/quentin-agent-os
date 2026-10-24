from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.execution.skill_executor import Executor, StepExecutionRecord
from quentin.cognitive.context_snapshots.base import SnapshotBlock


class _StubRegistry:
    def collect_all(self, repo_root, context, max_total_bytes=32768):  # type: ignore[no-untyped-def]
        _ = (repo_root, context, max_total_bytes)
        return [SnapshotBlock(id="stub", title="Stub Snapshot", content="snapshot-content")]


@pytest.mark.asyncio
async def test_prompt_contains_runtime_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS", "1")
    monkeypatch.setenv("QUENTIN_TOOL_CALL_PROTOCOLS", "0")

    captured = {}

    def _fake_build_layered_system_prompt(*, base_system, soul, skill, project_context, hints):  # type: ignore[no-untyped-def]
        _ = (soul, skill, project_context, hints)
        captured["base_system"] = base_system
        return "system"

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","result":"done"}'

    class _StubRouter:
        def route(self, mode, task_type):  # type: ignore[no-untyped-def]
            _ = (mode, task_type)
            return SimpleNamespace(provider="openai", name="gpt-test")

    monkeypatch.setattr("quentin.execution.skill_executor.get_context_snapshot_registry", lambda: _StubRegistry())
    monkeypatch.setattr("quentin.execution.skill_executor.build_layered_system_prompt", _fake_build_layered_system_prompt)
    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

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

    assert "RUNTIME SNAPSHOT" in captured.get("base_system", "")
    assert "snapshot-content" in captured.get("base_system", "")

