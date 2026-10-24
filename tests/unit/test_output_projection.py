from __future__ import annotations

from quentin.runtime.output_projection import (
    visible_output_from_brain_events,
    has_message_final_brain_event,
)
from quentin.runtime.system_events import BrainEvent


def _ev(*, typ: str, seq: int, payload: dict):
    return BrainEvent(
        event_id=f"e{seq}",
        session_id="s1",
        event_type=typ,
        category="message",
        phase="delta" if typ.endswith("delta") else "final",
        created_at="2026-01-01T00:00:00Z",
        source="test",
        turn_id="t1",
        seq=seq,
        payload=payload,
    )


def test_visible_output_prefers_message_final() -> None:
    events = [
        _ev(typ="message.delta", seq=1, payload={"chunk": "hello "}),
        _ev(typ="message.delta", seq=2, payload={"chunk": "world"}),
        _ev(typ="message.final", seq=3, payload={"text": "hello world!"}),
    ]
    assert visible_output_from_brain_events(events) == "hello world!"


def test_visible_output_reconstructs_from_deltas_when_no_final() -> None:
    events = [
        _ev(typ="message.delta", seq=2, payload={"chunk": "world"}),
        _ev(typ="message.delta", seq=1, payload={"chunk": "hello "}),
    ]
    assert visible_output_from_brain_events(events) == "hello world"


def test_visible_output_filters_by_turn_id() -> None:
    events = [
        BrainEvent(
            event_id="e1",
            session_id="s1",
            event_type="message.final",
            category="message",
            phase="final",
            created_at="2026-01-01T00:00:00Z",
            source="test",
            turn_id="t1",
            seq=1,
            payload={"text": "old"},
        ),
        BrainEvent(
            event_id="e2",
            session_id="s1",
            event_type="message.final",
            category="message",
            phase="final",
            created_at="2026-01-01T00:00:01Z",
            source="test",
            turn_id="t2",
            seq=2,
            payload={"text": "new"},
        ),
    ]
    assert visible_output_from_brain_events(events, turn_id="t2") == "new"


def test_visible_output_turn_filter_fallbacks_when_turn_absent() -> None:
    events = [
        _ev(typ="message.final", seq=1, payload={"text": "hello"}),
    ]
    assert visible_output_from_brain_events(events, turn_id="missing") == "hello"


def test_has_message_final_brain_event_true_for_selected_turn() -> None:
    events = [
        BrainEvent(
            event_id="e1",
            session_id="s1",
            event_type="message.final",
            category="message",
            phase="final",
            created_at="2026-01-01T00:00:00Z",
            source="test",
            turn_id="t2",
            seq=1,
            payload={"text": ""},
        ),
    ]
    assert has_message_final_brain_event(events, turn_id="t2") is True


def test_has_message_final_brain_event_false_without_final() -> None:
    events = [
        _ev(typ="message.delta", seq=1, payload={"chunk": "hello"}),
    ]
    assert has_message_final_brain_event(events, turn_id="t1") is False
