from __future__ import annotations

from quentin.infra.sessions.session_store import SessionStore
from quentin.memory.session_deltas import SessionDeltaConfig, SessionDeltaWriter


class _DummyMemory:
    def __init__(self) -> None:
        self.writes = []

    def remember_atomic(self, **kwargs):
        self.writes.append(kwargs)


class _AllowKernel:
    class _Result:
        allow = True

    def guard_action(self, action):
        return self._Result()


def test_session_delta_updates_state_cursors(tmp_path) -> None:
    mem = _DummyMemory()
    store = SessionStore(repo_root=tmp_path)
    cfg = SessionDeltaConfig(
        enabled=True,
        throttle_seconds=999,
        min_events=1,
        delta_bytes=1,
        delta_messages=1,
    )
    writer = SessionDeltaWriter(
        memory_fabric=mem,
        safety_kernel=_AllowKernel(),
        config=cfg,
        session_store=store,
    )

    writer.observe_execution(
        session_id="s-delta",
        trace_id="t-1",
        attempt_index=1,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="plan",
        actions_summary="act",
        final_output="done",
    )

    assert len(mem.writes) == 1
    state = store.load("s-delta")
    assert state.metadata.get("last_trace_id") == "t-1"
    assert state.deltas_cursor.get("pending_bytes", -1) == 0
    assert state.dirty_flags.get("session_delta") is False
