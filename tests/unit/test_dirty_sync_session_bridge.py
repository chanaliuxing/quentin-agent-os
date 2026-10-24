from __future__ import annotations

import json
from pathlib import Path

from quentin.infra.sessions.dirty_sync import DirtySyncManager, build_memory_sync_callback
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery


class _DummyEmbeddingClient:
    def __init__(self) -> None:
        self.calls = 0

    def embed_text(self, text: str):
        self.calls += 1
        n = float(len(text))
        return [n, n + 1.0]

    @property
    def dim(self) -> int:
        return 2


def _flush_now(mgr: DirtySyncManager, session_id: str) -> None:
    with mgr._lock:  # noqa: SLF001
        t = mgr._timers.get(session_id)
    if t:
        t.cancel()
    mgr._do_sync(session_id)  # noqa: SLF001


def _append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def test_dirty_sync_bridge_indexes_session_transcript_deltas(tmp_path: Path, monkeypatch) -> None:
    transcript = tmp_path / "session-1.jsonl"
    _append_jsonl(transcript, {"type": "message", "message": {"role": "user", "content": "u1"}})
    _append_jsonl(transcript, {"type": "message", "message": {"role": "assistant", "content": "a1"}})

    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=_DummyEmbeddingClient())
    callback = build_memory_sync_callback(memory_fabric=fabric, repo_root=tmp_path)
    mgr = DirtySyncManager(sync_callback=callback, debounce_sec=999.0, dedupe_ttl_sec=60.0)

    mgr.track_change("s1", {"file_path": str(transcript), "content_hash": "h1"})
    _flush_now(mgr, "s1")

    first = fabric.recall(MemoryQuery(text="u1", mode="text_only", top_k=20))
    first_session = [r for r in first if str(r.source).startswith("session_file:")]
    assert first_session

    _append_jsonl(transcript, {"type": "message", "message": {"role": "user", "content": "u2"}})
    mgr.track_change("s1", {"file_path": str(transcript), "content_hash": "h2"})
    _flush_now(mgr, "s1")

    second = fabric.recall(MemoryQuery(text="u2", mode="text_only", top_k=20))
    second_session = [r for r in second if str(r.source).startswith("session_file:")]
    assert second_session
