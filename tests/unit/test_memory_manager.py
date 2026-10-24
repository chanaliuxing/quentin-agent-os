from __future__ import annotations

from pathlib import Path

from quentin.memory.manager import MemoryManager, MemoryManagerConfig


class _FakeFabric:
    def __init__(self) -> None:
        self.calls = []

    def sync_memory_files(self, **kwargs):  # noqa: ANN003
        self.calls.append(("sync_memory_files", dict(kwargs)))
        return {"indexed": 1, "skipped": 0, "errors": 0, "stale_deleted": 0}

    def sync_session_file_delta(self, file_path):  # noqa: ANN001
        self.calls.append(("sync_session_file_delta", str(file_path)))
        return {"status": "indexed", "path": str(file_path), "offset": 10}


def test_memory_manager_run_sync_cycle(tmp_path: Path) -> None:
    fabric = _FakeFabric()
    mgr = MemoryManager(memory_fabric=fabric, repo_root=tmp_path)
    t1 = tmp_path / "s1.jsonl"
    t1.write_text("", encoding="utf-8")
    mgr.register_session_transcript(session_id="s1", transcript_path=t1)
    out = mgr.run_sync_cycle(force=False)
    assert "memory_files" in out
    assert "session_files" in out
    assert out["session_files"]["s1"]["indexed"] == 1


def test_memory_manager_session_start_and_pre_search(tmp_path: Path) -> None:
    fabric = _FakeFabric()
    cfg = MemoryManagerConfig(sync_on_session_start=True, sync_on_search=True)
    mgr = MemoryManager(memory_fabric=fabric, repo_root=tmp_path, config=cfg)
    t1 = tmp_path / "s2.jsonl"
    t1.write_text("", encoding="utf-8")
    mgr.on_session_start(session_id="s2", transcript_path=t1)
    mgr.maybe_sync_before_search()
    kinds = [k for k, _ in fabric.calls if k == "sync_memory_files"]
    assert len(kinds) >= 2


def test_memory_manager_status_contains_health(tmp_path: Path) -> None:
    fabric = _FakeFabric()
    mgr = MemoryManager(memory_fabric=fabric, repo_root=tmp_path)
    s = mgr.status()
    assert "config" in s
    assert "last_sync_result" in s
