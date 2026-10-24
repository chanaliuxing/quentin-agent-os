from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.cognitive.loop_maintenance import initialize_loop
from quentin.memory.models import MemoryQuery


class _FakeMemoryFabric:
    def __init__(self) -> None:
        self.calls = []
        self.pre_search_hook = None
        self.runtime_config = SimpleNamespace(dirty_debounce_sec=1.0, dirty_dedupe_ttl_sec=10.0)

    def set_pre_search_sync_hook(self, hook):  # noqa: ANN001
        self.pre_search_hook = hook

    def sync_memory_files(self, **kwargs):  # noqa: ANN003
        self.calls.append(("sync_memory_files", dict(kwargs)))
        return {"indexed": 1, "skipped": 0, "errors": 0, "stale_deleted": 0}

    def sync_session_file_delta(self, file_path):  # noqa: ANN001
        self.calls.append(("sync_session_file_delta", str(file_path)))
        return {"status": "indexed", "path": str(file_path), "offset": 10}


class _FakeToolManager:
    def register_tool(self, spec, handler):  # noqa: ANN001
        _ = (spec, handler)


def test_initialize_loop_wires_memory_manager_pre_search_hook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("quentin.tools.subagents.create_subagent_pack", lambda loop: [])
    loop = SimpleNamespace()
    fabric = _FakeMemoryFabric()
    initialize_loop(
        loop,
        repo_root=tmp_path,
        planner=object(),
        executor=object(),
        cognitive_policies=object(),
        goal_manager=object(),
        memory_fabric=fabric,
        traces_store=SimpleNamespace(append=lambda _: None),
        skill_manager=object(),
        model_router=object(),
        done_council=object(),
        reflection_council=object(),
        immune_loop=object(),
        safety_kernel=object(),
        system_event_queue=object(),
        council_manager=object(),
        tool_manager=_FakeToolManager(),
        self_programming_engine=object(),
    )

    assert callable(fabric.pre_search_hook)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    loop.memory_manager.on_session_start(session_id="s1", transcript_path=transcript)
    out = fabric.pre_search_hook(query=MemoryQuery(text="probe", mode="text_only", top_k=3))
    assert isinstance(out, dict)
    kinds = [k for k, _ in fabric.calls]
    assert "sync_memory_files" in kinds
    assert "sync_session_file_delta" in kinds
