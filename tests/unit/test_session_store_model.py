from __future__ import annotations

import asyncio

from quentin.infra.concurrency.abort_signal import abort_registry
from quentin.infra.concurrency.lane_orchestrator import LaneOrchestrator
from quentin.infra.sessions.session_store import SessionPolicy, SessionStore


def test_session_store_persists_and_recovers(tmp_path) -> None:
    store = SessionStore(repo_root=tmp_path)
    state = store.load_or_create("s-recover", metadata={"origin": "unit"})
    state.history.append({"role": "user", "content": "hello"})
    state.summary = "initial"
    state.touch()
    store.save(state)

    reloaded = store.load("s-recover")
    assert reloaded.session_id == "s-recover"
    assert reloaded.metadata.get("origin") == "unit"
    assert reloaded.history[-1]["content"] == "hello"
    assert reloaded.summary == "initial"


def test_session_store_disabled_uses_memory_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_SESSION_STORE_ENABLED", "0")
    store = SessionStore(repo_root=tmp_path)
    state = store.load_or_create("s-mem")
    state.summary = "mem-only"
    state.touch()
    store.save(state)
    reloaded = store.load("s-mem")
    assert reloaded.summary == "mem-only"
    assert store.state_file_path("s-mem").exists() is False


def test_session_policy_compaction_predictable(tmp_path) -> None:
    store = SessionStore(repo_root=tmp_path)
    sid = "s-compact"
    state = store.load_or_create(sid)
    for i in range(7):
        state.history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"})
    state.touch()
    store.save(state)

    policy = SessionPolicy(
        max_history_messages=5,
        max_history_chars=99999,
        keep_recent_messages=2,
        summary_max_chars=300,
        min_messages_to_compact=4,
    )
    compacted_state, report = store.maybe_compact(sid, policy=policy)

    assert report.compacted is True
    assert report.reason == "messages_overflow"
    assert compacted_state.compaction.compaction_count == 1
    assert compacted_state.history[0]["metadata"]["session_compaction"] is True
    assert compacted_state.history[0]["content"].startswith("[[SESSION_COMPACTION_GIST]]")
    assert len(compacted_state.history) == 3


def test_lane_orchestrator_run_in_session_uses_session_model(tmp_path) -> None:
    store = SessionStore(repo_root=tmp_path)
    state = store.load_or_create("s-lane")
    state.abort_signal_id = "abort-s-lane"
    store.save(state)

    orchestrator = LaneOrchestrator()

    async def _job() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    out = asyncio.run(
        orchestrator.run_in_session(
            state,
            _job,
            session_store=store,
            abort_existing=True,
        )
    )
    assert out == "ok"
    assert abort_registry.get_signal("abort-s-lane").is_aborted is True
