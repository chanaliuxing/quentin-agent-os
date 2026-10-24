from __future__ import annotations

import time

from quentin.infra.sessions.dirty_sync import DirtySyncManager


def _flush_now(mgr: DirtySyncManager, session_id: str) -> None:
    with mgr._lock:  # noqa: SLF001 - test private state for deterministic flush
        t = mgr._timers.get(session_id)
    if t:
        t.cancel()
    mgr._do_sync(session_id)  # noqa: SLF001 - test internal sync behavior directly


def test_dirty_sync_dedupes_same_file_hash_across_sessions() -> None:
    calls = []
    mgr = DirtySyncManager(
        sync_callback=lambda sid, data: calls.append((sid, dict(data))),
        debounce_sec=999.0,
        dedupe_ttl_sec=60.0,
    )

    delta = {"file_path": "src/a.py", "content_hash": "abc123", "final_output": "x"}
    mgr.track_change("s1", delta)
    _flush_now(mgr, "s1")
    mgr.track_change("s2", delta)
    _flush_now(mgr, "s2")

    assert len(calls) == 1
    assert calls[0][0] == "s1"


def test_dirty_sync_allows_new_hash_for_same_file() -> None:
    calls = []
    mgr = DirtySyncManager(
        sync_callback=lambda sid, data: calls.append((sid, dict(data))),
        debounce_sec=999.0,
        dedupe_ttl_sec=60.0,
    )

    mgr.track_change("s1", {"file_path": "src/a.py", "content_hash": "h1"})
    _flush_now(mgr, "s1")
    mgr.track_change("s2", {"file_path": "src/a.py", "content_hash": "h2"})
    _flush_now(mgr, "s2")

    assert len(calls) == 2


def test_dirty_sync_dedupe_ttl_expiry() -> None:
    calls = []
    mgr = DirtySyncManager(
        sync_callback=lambda sid, data: calls.append((sid, dict(data))),
        debounce_sec=999.0,
        dedupe_ttl_sec=0.01,
    )

    delta = {"file_path": "src/a.py", "content_hash": "abc123"}
    mgr.track_change("s1", delta)
    _flush_now(mgr, "s1")
    time.sleep(0.02)
    mgr.track_change("s2", delta)
    _flush_now(mgr, "s2")

    assert len(calls) == 2
