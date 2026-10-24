from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from quentin.cognitive.loop_impl import CognitiveLoop
from quentin.cognitive.loop_goal_flow import run_goal_internal
from quentin.cognitive.loop_orchestration import PreparedRunContext
from quentin.cognitive.self_awareness import SelfAwarenessSnapshot
from quentin.goals.done_definition import DoneCheckResult
from quentin.runtime.system_events import SystemEventQueue
from quentin.tools.manager import ToolCallContext, ToolManager
from quentin.tools.schemas import ToolCallRequest


class _DummyTraceRecorder:
    def record_event(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


def test_system_event_queue_drain_once(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    q.enqueue_event(
        session_id="s1",
        event_type="self_programming_patch_applied",
        payload={"gap_id": "g1", "patch_id": "p1"},
        source="test",
    )
    first = q.drain_events(session_id="s1", limit=10)
    second = q.drain_events(session_id="s1", limit=10)
    assert len(first) == 1
    assert first[0].event_type == "self_programming_patch_applied"
    assert second == []


def test_cognitive_loop_injects_and_drains_system_events(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M3_SYSTEM_EVENTS", "1")
    q = SystemEventQueue(repo_root=tmp_path)
    q.enqueue_event(
        session_id="global",
        event_type="self_programming_patch_applied",
        payload={"gap_id": "g2", "patch_id": "p2", "status": "applied"},
        source="self_programming_engine_v2",
    )

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.system_event_queue = q
    loop.trace_recorder = _DummyTraceRecorder()

    text1 = loop._drain_system_events_for_planner(session_id="sX")
    text2 = loop._drain_system_events_for_planner(session_id="sX")

    assert "System events completed in background" in text1
    assert "self_programming_patch_applied" in text1
    assert text2 == ""


def test_cognitive_loop_emits_self_awareness_alert(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.system_event_queue = q

    snapshot = SelfAwarenessSnapshot(
        status="warning",
        failure_rate=0.5,
        total_attempts=2,
        error_attempts=1,
        consecutive_system_errors=0,
        degrade_mode=False,
        self_programming_enabled=True,
        last_error="Interactive command blocked",
        failover_reason=None,
        anti_pattern_reason="interactive_editor_command",
        recent_failover_reasons=[],
        consecutive_no_progress=1,
        suggested_actions=["switch_to_fs_read_and_write_flow"],
        generated_at="2026-02-10T00:00:00+00:00",
    )
    goal = type("Goal", (), {"goal_id": "g1"})()

    loop._emit_self_awareness_event(
        session_id="s1",
        goal=goal,
        attempt_index=2,
        snapshot=snapshot,
    )

    events = q.drain_events(session_id="s1", limit=10)
    assert len(events) == 1
    assert events[0].event_type == "self_awareness_alert"
    assert events[0].payload.get("anti_pattern_reason") == "interactive_editor_command"


def test_system_event_formatter_includes_runtime_mode_fields(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    q.enqueue_event(
        session_id="s1",
        event_type="brain_guardrail_activated",
        payload={
            "status": "critical",
            "reason": "interactive_editor_command",
            "runtime_mode": "guardrail",
            "guardrail_remaining_sec": 42.5,
        },
        source="brain_daemon",
    )
    events = q.drain_events(session_id="s1", limit=10)
    text = SystemEventQueue.format_events_for_prompt(events, max_chars=2000)
    assert "runtime_mode=guardrail" in text
    assert "guardrail_remaining_sec=42.5" in text


def test_brain_event_subscribe_and_drain_fail_closed(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    seen = []

    def _bad_cb(_event):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    def _good_cb(event):  # type: ignore[no-untyped-def]
        seen.append(event.event_type)

    q.subscribe_session("s1", _bad_cb)
    q.subscribe_session("s1", _good_cb)

    q.emit_brain_event(
        session_id="s1",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={"a": 1},
        turn_id="t1",
    )
    q.emit_brain_event(
        session_id="s1",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={"text": "ok"},
        turn_id="t1",
    )

    drained = q.drain_brain_events(session_id="s1", limit=10)
    public = [e for e in drained if str(e.event_type or "") != "subscriber_diagnostic"]
    assert [e.event_type for e in public] == ["turn_start", "message"]
    assert len(public) == 2
    assert int(public[0].seq) < int(public[1].seq)
    seen_public = [t for t in seen if t != "subscriber_diagnostic"]
    assert seen_public == ["turn_start", "message"]
    stats = q.get_subscriber_stats(session_id="s1")
    assert stats
    assert int(stats[0].get("failures_total") or 0) >= 1
    assert str(stats[0].get("last_error") or "").strip() != ""


def test_brain_event_cursor_replay(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    first = q.emit_brain_event(
        session_id="s1",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="t1",
    )
    q.emit_brain_event(
        session_id="s1",
        event_type="message",
        category="message",
        phase="update",
        source="test",
        payload={},
        turn_id="t1",
    )
    replay = q.drain_brain_events(session_id="s1", after_cursor=first.cursor, limit=10)
    assert len(replay) == 1
    assert replay[0].event_type == "message"


def test_brain_event_ack_cursor_monotonic(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    e1 = q.emit_brain_event(
        session_id="s1",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="t1",
    )
    e2 = q.emit_brain_event(
        session_id="s1",
        event_type="turn_end",
        category="turn",
        phase="end",
        source="test",
        payload={},
        turn_id="t1",
    )
    stored1 = q.ack_cursor(session_id="s1", cursor=e2.cursor)
    stored2 = q.ack_cursor(session_id="s1", cursor=e1.cursor)
    assert stored1 == e2.cursor
    assert stored2 == e2.cursor
    assert q.get_acked_cursor(session_id="s1") == e2.cursor


def test_subscribe_session_failures_emit_diagnostic_and_do_not_break(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    received = []

    def _bad(_event):  # type: ignore[no-untyped-def]
        raise RuntimeError("bad")

    def _good(event):  # type: ignore[no-untyped-def]
        received.append(event.event_type)

    q.subscribe_session("s-diag", _bad)
    q.subscribe_session("s-diag", _good)
    for _ in range(5):
        q.emit_brain_event(
            session_id="s-diag",
            event_type="message",
            category="message",
            phase="update",
            source="test",
            payload={},
            turn_id="t1",
        )
    events = q.list_brain_events(session_id="s-diag", limit=200)
    assert any(e.event_type == "subscriber_diagnostic" for e in events)
    assert len(received) >= 3
    stats = q.get_subscriber_stats(session_id="s-diag")
    assert any(int(s.get("failures_total") or 0) >= 1 for s in stats)


def test_concurrent_100_sessions_seq_monotonic(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)

    def _emit_for_session(idx: int) -> None:
        sid = f"s-{idx}"
        for turn in range(8):
            q.emit_brain_event(
                session_id=sid,
                event_type="tool_execution_start",
                category="tool",
                phase="start",
                source="test",
                payload={"turn": turn},
                turn_id=f"t-{turn}",
            )

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_emit_for_session, range(100)))

    for idx in range(100):
        sid = f"s-{idx}"
        events = q.list_brain_events(session_id=sid, limit=200)
        assert len(events) == 8
        assert all(int(events[i].seq) < int(events[i + 1].seq) for i in range(7))


def test_list_brain_events_does_not_consume_queue(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)
    q.emit_brain_event(
        session_id="s1",
        event_type="message.final",
        category="message",
        phase="final",
        source="test",
        payload={"text": "hello"},
        turn_id="t1",
    )
    listed = q.list_brain_events(session_id="s1", limit=10)
    assert len(listed) == 1
    drained = q.drain_brain_events(session_id="s1", limit=10)
    assert len(drained) == 1
    assert drained[0].event_type == "message.final"


def test_subscriber_circuit_open_emits_diagnostic_and_drops(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_SUBSCRIBER_CIRCUIT_THRESHOLD", "1")
    q = SystemEventQueue(repo_root=tmp_path)

    def _bad_cb(_event):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom-on-purpose")

    q.subscribe_session("s-circuit", _bad_cb)
    q.emit_brain_event(
        session_id="s-circuit",
        event_type="turn_start",
        category="turn",
        phase="start",
        source="test",
        payload={},
        turn_id="t1",
    )
    q.emit_brain_event(
        session_id="s-circuit",
        event_type="turn_end",
        category="turn",
        phase="end",
        source="test",
        payload={},
        turn_id="t1",
    )

    stats = q.get_subscriber_stats(session_id="s-circuit")
    assert stats
    assert int(stats[0].get("failures_total") or 0) >= 1
    assert int(stats[0].get("dropped_total") or 0) >= 1
    assert bool(stats[0].get("is_circuit_open")) is True

    events = q.list_brain_events(session_id="s-circuit", limit=50)
    assert any(str(e.event_type or "") == "subscriber_diagnostic" for e in events)


def test_concurrent_many_sessions_keep_seq_monotonic(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)

    async def _emit_many() -> dict[str, list[int]]:
        async def _run_session(idx: int) -> tuple[str, list[int]]:
            sid = f"s{idx:03d}"
            seqs: list[int] = []
            for step in range(4):
                ev = q.emit_brain_event(
                    session_id=sid,
                    event_type="tool_execution_end",
                    category="tool",
                    phase="end",
                    source="test",
                    payload={"step": step},
                    turn_id=f"t{idx}",
                )
                seqs.append(int(ev.seq))
                await asyncio.sleep(0)
            return sid, seqs

        rows = await asyncio.gather(*[_run_session(i) for i in range(120)])
        return {sid: seqs for sid, seqs in rows}

    matrix = asyncio.run(_emit_many())
    assert len(matrix) == 120
    for seqs in matrix.values():
        assert len(seqs) == 4
        assert all(seqs[i] < seqs[i + 1] for i in range(3))


def test_tool_manager_emits_tool_execution_lifecycle_events(tmp_path: Path) -> None:
    tm = ToolManager()
    q = SystemEventQueue(repo_root=tmp_path)
    tm.set_event_queue(q)

    def _echo(params):  # type: ignore[no-untyped-def]
        return {"status": "ok", "echo": params.get("x")}

    tm.register("demo.echo", _echo)
    res = asyncio.run(
        tm.call_tool(
            ToolCallRequest(tool_name="demo.echo", payload={"x": 7}),
            ctx=ToolCallContext(metadata={"session_id": "s1", "turn_id": "turn-1"}),
        )
    )
    assert res.success is True

    events = q.drain_brain_events(session_id="s1", limit=20)
    tool_events = [e for e in events if e.category == "tool"]
    assert tool_events
    assert tool_events[0].event_type == "tool_execution_start"
    assert tool_events[-1].event_type == "tool_execution_end"
    assert tool_events[-1].payload.get("success") is True


def test_run_goal_internal_emits_turn_sequence_events(tmp_path: Path) -> None:
    q = SystemEventQueue(repo_root=tmp_path)

    class _FakeLoop:
        def __init__(self):
            self.repo_root = tmp_path
            self.system_event_queue = q
            self.model_router = None
            self.memory_fabric = None
            self.degrade_mode = False
            self.self_programming_enabled = False

        async def _prepare_run_context(self, **kwargs):  # type: ignore[no-untyped-def]
            return PreparedRunContext(
                session_id="s1",
                goal=SimpleNamespace(goal_id="g1"),
                historical_context="",
                perception_data={},
                executor=None,
                idempotency=None,
                early_result=None,
            )

        def _run_checkpoint(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        async def _check_context_and_flush(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        async def _run_single_attempt(self, **kwargs):  # type: ignore[no-untyped-def]
            state = kwargs.get("state")
            if state is not None:
                state.final_output = "done"
                state.actions_summary = "ok"
                state.done_result = DoneCheckResult(is_done=True, confidence=1.0, reasons=["done"])
            return "break"

        def _finalize_goal_result(self, **kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(done=True, final_output="done")

    task = SimpleNamespace(
        metadata={"session_id": "s1", "think_level": "off"},
        task_id="turn-1",
        input_text="hello",
        domain="core",
        environment="sandbox",
        history=[],
    )
    loop = _FakeLoop()
    out = asyncio.run(run_goal_internal(loop, task=task))
    assert out.done is True

    events = q.drain_brain_events(session_id="s1", limit=50)
    types = [e.event_type for e in events]
    assert "turn_start" in types
    assert "turn_attempt_start" in types
    assert "turn_attempt_end" in types
    assert "message" in types
    assert types[-1] == "turn_end"
