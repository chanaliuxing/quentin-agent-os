from __future__ import annotations

import asyncio
from types import SimpleNamespace

from quentin.execution.skill_executor import Executor, StepExecutionRecord
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.tool_knowledge import ToolKnowledgeEntry


class _DummyRouter:
    def route(self, mode: str = "", task_type: str = "generic"):
        _ = (mode, task_type)
        return SimpleNamespace(provider="ollama", name="dummy-model")


def test_executor_injects_tool_knowledge_block_into_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_PROMPT", "1")
    monkeypatch.setenv("QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_TOP_K", "4")

    captured = {"system_prompt": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["system_prompt"] = str(kwargs.get("system_prompt") or "")
        return '{"status":"ok","result":"ok","call_tool":null}'

    monkeypatch.setattr("quentin.execution.skill_executor.call_llm", _fake_call_llm)

    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    mf = MemoryFabric(repo_root=tmp_path)
    entry = ToolKnowledgeEntry(
        tool_name="fs.read_file",
        signature="fs.read_file(path)",
        description="Read file text.",
        examples=[{"input": {"path": "README.md"}, "output": "ok"}],
        stats={"call_count": 3, "success_rate": 1.0, "last_used_at": "2026-02-22T00:00:00Z"},
    )
    mf.store.add(entry.to_memory_record(tier=MemoryTier.LTS))

    executor = Executor(repo_root=tmp_path, model_router=_DummyRouter(), tool_manager=None)
    record = StepExecutionRecord(
        step_id="s1",
        description="inspect repo",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    asyncio.run(
        executor._fallback_llm_execute(
            step={"step_id": "s1", "description": "inspect repo"},
            goal={"domain": "core", "environment": "sandbox"},
            context={},
            record=record,
        )
    )

    assert "TOOL KNOWLEDGE (learned usage):" in captured["system_prompt"]
    assert "fs.read_file" in captured["system_prompt"]
    assert "call_count=3" in captured["system_prompt"]
