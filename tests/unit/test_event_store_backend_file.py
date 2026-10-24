from __future__ import annotations

import os

from quentin.runtime.event_store.file_backend import FileEventStoreBackend
from quentin.runtime.system_events import SystemEventQueue


def test_file_event_store_backend_enqueue_peek_drain(tmp_path) -> None:
    b = FileEventStoreBackend(repo_root=tmp_path)

    b.enqueue_event({"session_id": "s1", "event_type": "x", "payload": {"a": 1}})
    b.enqueue_event({"session_id": "s1", "event_type": "y", "payload": {"b": 2}})
    b.enqueue_event({"session_id": "s2", "event_type": "z", "payload": {"c": 3}})

    peek_s1 = b.peek_events("s1", limit=10)
    assert [e.get("event_type") for e in peek_s1] == ["x", "y"]

    drained_s1 = b.drain_events("s1", limit=1)
    assert [e.get("event_type") for e in drained_s1] == ["x"]

    peek_s1_after = b.peek_events("s1", limit=10)
    assert [e.get("event_type") for e in peek_s1_after] == ["y"]

    drained_s1_rest = b.drain_events("s1", limit=10)
    assert [e.get("event_type") for e in drained_s1_rest] == ["y"]
    assert b.peek_events("s1", limit=10) == []


def test_system_event_queue_backend_selection_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "noop")
    q = SystemEventQueue(repo_root=tmp_path)
    q.enqueue_event(session_id="s1", event_type="x", payload={"a": 1})
    assert q.list_events(session_id="s1", limit=10) == []
    assert q.drain_events(session_id="s1", limit=10) == []

