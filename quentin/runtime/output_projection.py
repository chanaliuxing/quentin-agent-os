from __future__ import annotations

from typing import Iterable, List

from quentin.runtime.system_events import BrainEvent


def _select_events_for_turn(events: List[BrainEvent], *, turn_id: str = "") -> List[BrainEvent]:
    tid = str(turn_id or "").strip()
    if not tid:
        return events
    scoped = [e for e in events if str(getattr(e, "turn_id", "") or "") == tid]
    return scoped or events


def has_message_final_brain_event(events: Iterable[BrainEvent], *, turn_id: str = "") -> bool:
    rows: List[BrainEvent] = [e for e in events if isinstance(e, BrainEvent)]
    if not rows:
        return False
    rows = _select_events_for_turn(rows, turn_id=turn_id)
    return any(str(e.event_type or "") == "message.final" for e in rows)


def visible_output_from_brain_events(events: Iterable[BrainEvent], *, turn_id: str = "") -> str:
    rows: List[BrainEvent] = [e for e in events if isinstance(e, BrainEvent)]
    if not rows:
        return ""
    rows = _select_events_for_turn(rows, turn_id=turn_id)

    finals = [e for e in rows if str(e.event_type or "") == "message.final"]
    if finals:
        payload = finals[-1].payload if isinstance(finals[-1].payload, dict) else {}
        return str(payload.get("text") or "").strip()

    deltas = [e for e in rows if str(e.event_type or "") == "message.delta"]
    if deltas:
        deltas = sorted(deltas, key=lambda x: int(x.seq or 0))
        text = "".join(str((e.payload or {}).get("chunk") or "") for e in deltas)
        return str(text or "").strip()

    return ""
