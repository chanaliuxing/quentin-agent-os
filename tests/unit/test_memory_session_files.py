from __future__ import annotations

import json
from pathlib import Path

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.session_files import (
    build_session_delta,
    build_session_entry,
    extract_session_text,
    session_path_for_file,
)


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


def _append_jsonl(path: Path, obj: dict, *, newline: bool = True) -> None:
    s = json.dumps(obj, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(s)
        if newline:
            f.write("\n")


def test_extract_session_text_supports_string_and_blocks() -> None:
    assert extract_session_text("  hello \n world  ") == "hello world"
    assert extract_session_text([{"type": "text", "text": " a  "}, {"type": "image", "url": "x"}]) == "a"
    assert extract_session_text([{"type": "image", "url": "x"}]) is None


def test_build_session_entry_filters_to_user_assistant_messages(tmp_path: Path) -> None:
    path = tmp_path / "s1.jsonl"
    _append_jsonl(path, {"type": "message", "message": {"role": "user", "content": "hello"}})
    _append_jsonl(path, {"type": "message", "message": {"role": "tool", "content": "skip me"}})
    _append_jsonl(path, {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}})
    _append_jsonl(path, {"type": "event", "payload": {"x": 1}})

    entry = build_session_entry(path)
    assert entry is not None
    assert entry.path == session_path_for_file(path)
    assert entry.content == "User: hello\nAssistant: done"
    assert entry.hash


def test_build_session_delta_reads_only_new_complete_lines(tmp_path: Path) -> None:
    path = tmp_path / "s2.jsonl"
    _append_jsonl(path, {"type": "message", "message": {"role": "user", "content": "a"}})
    _append_jsonl(path, {"type": "message", "message": {"role": "assistant", "content": "b"}})

    d1 = build_session_delta(path, last_offset=0)
    assert d1 is not None
    assert d1.message_count == 2
    assert d1.content == "User: a\nAssistant: b"
    assert d1.next_offset == path.stat().st_size

    # Append partial JSON line (no trailing newline): should not be consumed yet.
    _append_jsonl(
        path,
        {"type": "message", "message": {"role": "user", "content": "partial"}},
        newline=False,
    )
    d2 = build_session_delta(path, last_offset=d1.next_offset)
    assert d2 is None

    # Complete the line and add a second line.
    with path.open("a", encoding="utf-8") as f:
        f.write("\n")
    _append_jsonl(path, {"type": "message", "message": {"role": "assistant", "content": "ok"}})

    d3 = build_session_delta(path, last_offset=d1.next_offset)
    assert d3 is not None
    assert d3.message_count == 2
    assert d3.content == "User: partial\nAssistant: ok"
    assert d3.next_offset == path.stat().st_size


def test_memory_fabric_sync_session_file_delta(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "s3.jsonl"
    _append_jsonl(path, {"type": "message", "message": {"role": "user", "content": "u1"}})
    _append_jsonl(path, {"type": "message", "message": {"role": "assistant", "content": "a1"}})

    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=_DummyEmbeddingClient())

    r1 = fabric.sync_session_file_delta(path, tier=MemoryTier.STS)
    assert r1["status"] == "indexed"
    first_offset = int(r1["offset"])
    assert first_offset > 0
    assert r1["message_count"] == 2

    r2 = fabric.sync_session_file_delta(path, tier=MemoryTier.STS)
    assert r2["status"] == "noop"
    assert int(r2["offset"]) == first_offset

    _append_jsonl(path, {"type": "message", "message": {"role": "user", "content": "u2"}})
    r3 = fabric.sync_session_file_delta(path, tier=MemoryTier.STS)
    assert r3["status"] == "indexed"
    assert int(r3["offset"]) > first_offset
    assert r3["message_count"] == 1
