from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_system_events_api_respects_noop_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "noop")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    q.enqueue_event(session_id="s-noop", event_type="background_task_completed", payload={"task_id": "t1"})

    client = TestClient(app)
    resp = client.get("/system-events", params={"session_id": "s-noop", "drain": False, "limit": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["events"] == []


def test_system_events_api_reads_file_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    q.enqueue_event(session_id="s-file", event_type="background_task_failed", payload={"task_id": "t2"})

    client = TestClient(app)
    resp = client.get("/system-events", params={"session_id": "s-file", "drain": False, "limit": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "background_task_failed"
    assert body["events"][0]["task_id"] == "t2"


def test_brain_events_drain_and_stream_cursor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    first = q.emit_brain_event(
        session_id="s-cursor",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="turn-1",
    )
    q.emit_brain_event(
        session_id="s-cursor",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "hello"},
        turn_id="turn-1",
    )

    client = TestClient(app)
    resp = client.get(
        "/brain-events/drain",
        params={"session_id": "s-cursor", "limit": 10, "after_cursor": first.cursor},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "message"
    assert str(body["next_cursor"] or "").strip() != ""

    with client.stream(
        "GET",
        "/brain-events/stream",
        params={"session_id": "s-cursor", "after_cursor": first.cursor, "timeout_s": 0.2, "max_batches": 1},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        text = "".join(list(stream_resp.iter_text()))
    assert "event: brain_event" in text
    lines = [ln for ln in text.splitlines() if ln.startswith("data: ")]
    payloads = []
    for line in lines:
        raw = str(line[len("data: ") :]).strip()
        if not raw.startswith("{"):
            continue
        try:
            payloads.append(json.loads(raw))
        except Exception:
            continue
    assert any(str(p.get("event_type") or "") == "message" for p in payloads)


def test_brain_events_drain_is_replay_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    q.emit_brain_event(
        session_id="s-replay",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "hello"},
        turn_id="turn-1",
    )

    client = TestClient(app)
    first = client.get("/brain-events/drain", params={"session_id": "s-replay", "limit": 10})
    second = client.get("/brain-events/drain", params={"session_id": "s-replay", "limit": 10})
    assert first.status_code == 200
    assert second.status_code == 200
    b1 = first.json()
    b2 = second.json()
    assert b1["count"] == 1
    assert b2["count"] == 1
    assert str(b1["events"][0]["event_id"]) == str(b2["events"][0]["event_id"])


def test_brain_events_dedupe_by_idempotency_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    payload = {
        "__brain_event_v1": {
            "event_id": "ev-1",
            "session_id": "s-dedupe",
            "event_type": "message.delta",
            "category": "message",
            "phase": "delta",
            "created_at": "2026-02-22T00:00:00Z",
            "source": "test",
            "turn_id": "t1",
            "seq": 1,
            "cursor": "1:ev-1",
            "idempotency_key": "idem-1",
            "payload": {"chunk": "a"},
        }
    }
    q.enqueue_event(session_id="s-dedupe", event_type="message.delta", payload=payload, source="test")
    q.enqueue_event(session_id="s-dedupe", event_type="message.delta", payload=payload, source="test")

    client = TestClient(app)
    resp = client.get("/brain-events/drain", params={"session_id": "s-dedupe", "limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1


def test_brain_events_replay_survives_queue_recreate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q1 = SystemEventQueue(repo_root=".")
    first = q1.emit_brain_event(
        session_id="s-restart",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="t1",
    )
    q1.emit_brain_event(
        session_id="s-restart",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "after"},
        turn_id="t1",
    )

    # Simulate process restart by re-creating queue object against same backend path.
    _q2 = SystemEventQueue(repo_root=".")

    client = TestClient(app)
    resp = client.get(
        "/brain-events/drain",
        params={"session_id": "s-restart", "after_cursor": first.cursor, "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "message"


def test_brain_events_ack_cursor_and_use_acked_cursor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    e1 = q.emit_brain_event(
        session_id="s-ack",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="turn-1",
    )
    q.emit_brain_event(
        session_id="s-ack",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "ack"},
        turn_id="turn-1",
    )

    client = TestClient(app)
    ack_resp = client.post("/brain-events/ack", params={"session_id": "s-ack", "cursor": e1.cursor})
    assert ack_resp.status_code == 200
    drain_resp = client.get("/brain-events/drain", params={"session_id": "s-ack", "use_acked_cursor": True, "limit": 10})
    assert drain_resp.status_code == 200
    body = drain_resp.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "message"


def test_brain_events_stream_use_acked_cursor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    e1 = q.emit_brain_event(
        session_id="s-stream-ack",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="turn-1",
    )
    q.emit_brain_event(
        session_id="s-stream-ack",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "next"},
        turn_id="turn-1",
    )
    q.ack_cursor(session_id="s-stream-ack", cursor=e1.cursor)

    client = TestClient(app)
    with client.stream(
        "GET",
        "/brain-events/stream",
        params={"session_id": "s-stream-ack", "use_acked_cursor": True, "timeout_s": 0.2, "max_batches": 1},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        text = "".join(list(stream_resp.iter_text()))

    lines = [ln for ln in text.splitlines() if ln.startswith("data: ")]
    payloads = []
    for line in lines:
        raw = str(line[len("data: ") :]).strip()
        if not raw.startswith("{"):
            continue
        try:
            payloads.append(json.loads(raw))
        except Exception:
            continue

    event_types = [str(p.get("event_type") or "") for p in payloads]
    assert "message" in event_types
    assert "turn_start" not in event_types


def test_run_task_silent_message_final_does_not_leak_raw_output(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    class _FakeLoop:
        def run_task(self, task):  # type: ignore[no-untyped-def]
            q = SystemEventQueue(repo_root=".")
            q.emit_brain_event(
                session_id=str((task.metadata or {}).get("session_id") or "api"),
                event_type="message.final",
                category="message",
                phase="final",
                source="test",
                payload={"text": "", "silent": True},
                turn_id=str(getattr(task, "task_id", "") or ""),
            )
            return SimpleNamespace(
                task_id=str(getattr(task, "task_id", "") or ""),
                goal_id="g-1",
                done=True,
                done_confidence=1.0,
                plan_summary="",
                actions_summary="",
                final_output="[[silent]] should-not-leak",
            )

    class _FakeContainer:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            self.cognitive_loop = _FakeLoop()

    async def _fake_run_in_lane(_session_id, coro_factory, **kwargs):  # type: ignore[no-untyped-def]
        return await coro_factory()

    monkeypatch.setattr("quentin.bootstrap.container.Container", _FakeContainer)
    monkeypatch.setattr(
        "quentin.infra.concurrency.lane_orchestrator.lane_orchestrator.run_in_lane",
        _fake_run_in_lane,
    )
    monkeypatch.setattr(
        "meta_agent.api.server.trace_recorder",
        SimpleNamespace(log_event=lambda *args, **kwargs: None),
    )

    client = TestClient(app)
    resp = client.post("/run-task", json={"input_text": "x", "session_id": "s-silent"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert str(body.get("final_output") or "") == ""


def test_brain_events_api_key_and_rate_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")
    monkeypatch.setenv("QUENTIN_BRAIN_EVENTS_API_KEY", "k-1")
    monkeypatch.setenv("QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN", "2")

    from meta_agent.api.server import app, _brain_events_rate_window

    _brain_events_rate_window.clear()
    client = TestClient(app)
    denied = client.get("/brain-events/drain", params={"session_id": "s-auth"})
    assert denied.status_code == 403

    ok1 = client.get("/brain-events/drain", params={"session_id": "s-auth", "api_key": "k-1"})
    ok2 = client.get("/brain-events/drain", params={"session_id": "s-auth", "api_key": "k-1"})
    assert ok1.status_code == 200
    assert ok2.status_code == 200
    limited = client.get("/brain-events/drain", params={"session_id": "s-auth", "api_key": "k-1"})
    assert limited.status_code == 200
    body = limited.json()
    assert bool(body.get("degraded")) is True
    assert str(body.get("degrade_reason") or "") == "rate_limit"
    assert int(body.get("retry_after_sec") or 0) >= 1


def test_brain_events_stream_rate_limit_degrades_with_observable_event(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")
    monkeypatch.setenv("QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN", "1")

    from meta_agent.api.server import app, _brain_events_rate_window
    from quentin.runtime.system_events import SystemEventQueue

    _brain_events_rate_window.clear()
    q = SystemEventQueue(repo_root=".")
    q.emit_brain_event(
        session_id="s-rate",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "x"},
        turn_id="t1",
    )

    client = TestClient(app)
    warm = client.get("/brain-events/drain", params={"session_id": "s-rate"})
    assert warm.status_code == 200
    with client.stream("GET", "/brain-events/stream", params={"session_id": "s-rate"}) as stream_resp:
        assert stream_resp.status_code == 200
        text = "".join(list(stream_resp.iter_text()))
    assert "event: degraded" in text
    assert '"degrade_reason": "rate_limit"' in text
    events = q.list_brain_events(session_id="default:s-rate", limit=20)
    assert any(str(e.event_type or "") == "gateway.rate_limited" for e in events)


def test_brain_events_drain_applies_backpressure_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")
    monkeypatch.setenv("QUENTIN_BRAIN_EVENTS_MAX_LIMIT", "2")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    for i in range(4):
        q.emit_brain_event(
            session_id="s-bp",
            event_type="message.delta",
            category="message",
            phase="delta",
            source="test",
            payload={"chunk": str(i)},
            turn_id="t1",
        )

    client = TestClient(app)
    resp = client.get("/brain-events/drain", params={"session_id": "s-bp", "limit": 1000})
    assert resp.status_code == 200
    body = resp.json()
    assert body["backpressure_applied"] is True
    assert int(body["effective_limit"]) == 2
    assert body["count"] == 2


def test_brain_events_tenant_scoped_isolation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    q.emit_brain_event(
        session_id="tenant-a:s-1",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "a"},
        turn_id="t1",
    )
    q.emit_brain_event(
        session_id="tenant-b:s-1",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "b"},
        turn_id="t1",
    )
    client = TestClient(app)
    ra = client.get("/brain-events/drain", params={"tenant_id": "tenant-a", "session_id": "s-1", "limit": 10})
    rb = client.get("/brain-events/drain", params={"tenant_id": "tenant-b", "session_id": "s-1", "limit": 10})
    assert ra.status_code == 200
    assert rb.status_code == 200
    ba = ra.json()
    bb = rb.json()
    assert ba["count"] == 1
    assert bb["count"] == 1
    assert ba["events"][0]["payload"].get("text") == "a"
    assert bb["events"][0]["payload"].get("text") == "b"
    assert ba["session_id"] == "tenant-a:s-1"
    assert bb["session_id"] == "tenant-b:s-1"


def test_brain_events_stream_backpressure_and_auto_ack(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    for idx in range(5):
        q.emit_brain_event(
            session_id="s-bp",
            event_type="message",
            category="message",
            phase="update",
            source="test",
            payload={"index": idx},
            turn_id="t1",
        )

    client = TestClient(app)
    with client.stream(
        "GET",
        "/brain-events/stream",
        params={
            "session_id": "s-bp",
            "timeout_s": 0.2,
            "max_batches": 1,
            "max_events": 2,
            "auto_ack": True,
        },
    ) as stream_resp:
        assert stream_resp.status_code == 200
        text = "".join(list(stream_resp.iter_text()))
    assert "event: backpressure" in text

    cursor = q.get_acked_cursor(session_id="s-bp")
    assert str(cursor or "").strip() != ""
    remaining = q.drain_brain_events(session_id="s-bp", after_cursor=cursor, limit=20)
    assert len(remaining) >= 1


def test_brain_events_duplicate_dedupe_and_resume_after_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file")

    from meta_agent.api.server import app
    from quentin.runtime.system_events import SystemEventQueue

    q = SystemEventQueue(repo_root=".")
    e1 = q.emit_brain_event(
        session_id="s-restart",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"n": 1},
        turn_id="t1",
    )
    # Inject a duplicate idempotency event manually.
    q.enqueue_event(
        session_id="s-restart",
        event_type=e1.event_type,
        source=e1.source,
        payload={
            "__brain_event_v2": {**e1.to_dict(), "payload": {"n": 1}},
            "__brain_event_v1": {**e1.to_dict(), "payload": {"n": 1}},
        },
    )
    e2 = q.emit_brain_event(
        session_id="s-restart",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"n": 2},
        turn_id="t1",
    )

    client = TestClient(app)
    first = client.get("/brain-events/drain", params={"session_id": "s-restart", "limit": 10, "dedupe": True})
    assert first.status_code == 200
    body = first.json()
    assert body["count"] == 2
    assert [int(x["payload"]["n"]) for x in body["events"]] == [1, 2]
    next_cursor = str(body["next_cursor"] or "")
    ack = client.post("/brain-events/ack", params={"session_id": "s-restart", "cursor": next_cursor})
    assert ack.status_code == 200

    # Simulate process restart by creating a fresh queue instance and adding one more event.
    q2 = SystemEventQueue(repo_root=".")
    q2.emit_brain_event(
        session_id="s-restart",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"n": 3},
        turn_id="t1",
    )
    resumed = client.get(
        "/brain-events/drain",
        params={"session_id": "s-restart", "use_acked_cursor": True, "dedupe": True, "limit": 10},
    )
    assert resumed.status_code == 200
    body2 = resumed.json()
    assert body2["count"] == 1
    assert int(body2["events"][0]["payload"]["n"]) == 3
    assert str(e2.cursor or "").strip() != str(body2["events"][0]["cursor"] or "").strip()
