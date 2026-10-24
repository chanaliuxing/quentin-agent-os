from __future__ import annotations

from quentin.infra.sessions.dirty_sync import DirtySyncManager


def test_dirty_sync_configure_updates_runtime_params() -> None:
    mgr = DirtySyncManager(sync_callback=lambda sid, data: None, debounce_sec=5.0, dedupe_ttl_sec=120.0)
    mgr.configure(debounce_sec=1.5, dedupe_ttl_sec=30.0)
    assert abs(mgr.debounce_sec - 1.5) < 1e-9
    assert abs(mgr.dedupe_ttl_sec - 30.0) < 1e-9
