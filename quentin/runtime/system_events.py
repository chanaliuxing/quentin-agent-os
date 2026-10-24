from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from collections import defaultdict
import json
import os
import re
import time
import uuid

from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.utils.time import now_utc_iso
from quentin.runtime.event_store.base import EventStoreBackend
from quentin.runtime.event_store import build_event_store_backend
from quentin.runtime.event_schema_registry import parse_brain_event_envelope


def _utc_now() -> str:
    return now_utc_iso()


def _safe_session_key(session_id: str) -> str:
    raw = str(session_id or "").strip() or "global"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)
    return cleaned or "global"

BACKGROUND_TASK_EVENT_TYPES = {
    "background_task_started",
    "background_task_completed",
    "background_task_failed",
    "background_task_cancelled",
    "background_task_timeout",
}


@dataclass
class BrainEvent:
    event_id: str
    session_id: str
    event_type: str
    category: str
    phase: str
    created_at: str
    source: str = ""
    turn_id: str = ""
    seq: int = 0
    cursor: str = ""
    idempotency_key: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_system_event_payload(self) -> Dict[str, Any]:
        data = self.to_dict()
        return {"__brain_event_v1": data, "__brain_event_v2": data}

    @classmethod
    def from_system_event(cls, event: "SystemEvent") -> "BrainEvent":
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw = parse_brain_event_envelope(payload)
        if isinstance(raw, dict):
            return cls(
                event_id=str(raw.get("event_id") or event.event_id),
                session_id=str(raw.get("session_id") or event.session_id),
                event_type=str(raw.get("event_type") or event.event_type),
                category=str(raw.get("category") or ""),
                phase=str(raw.get("phase") or ""),
                created_at=str(raw.get("created_at") or event.created_at),
                source=str(raw.get("source") or event.source),
                turn_id=str(raw.get("turn_id") or ""),
                seq=int(raw.get("seq") or 0),
                cursor=str(raw.get("cursor") or ""),
                idempotency_key=str(raw.get("idempotency_key") or raw.get("event_id") or event.event_id),
                payload=raw.get("payload") if isinstance(raw.get("payload"), dict) else {},
            )
        et = str(event.event_type or "")
        bits = et.split(".")
        category = bits[0] if bits else "system"
        phase = bits[-1] if len(bits) > 1 else "event"
        return cls(
            event_id=str(event.event_id or ""),
            session_id=str(event.session_id or "global"),
            event_type=et or "system.event",
            category=category,
            phase=phase,
            created_at=str(event.created_at or _utc_now()),
            source=str(event.source or ""),
            turn_id="",
            seq=0,
            cursor="",
            idempotency_key=str(event.event_id or ""),
            payload=payload,
        )


@dataclass
class SystemEvent:
    event_id: str
    session_id: str
    event_type: str
    created_at: str
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SystemEvent:
        return cls(
            event_id=str(data.get("event_id") or ""),
            session_id=str(data.get("session_id") or "global"),
            event_type=str(data.get("event_type") or "system_event"),
            created_at=str(data.get("created_at") or ""),
            source=str(data.get("source") or ""),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        )


class SystemEventQueue:
    """
    Lightweight per-session event queue persisted via EventStoreBackend (P2-C).
    Events are one-shot: `drain_events` consumes and removes returned events.
    P5: Upgraded to support Cross-Session Broadcast (Pub/Sub).
    """

    def __init__(self, repo_root: str | Path = ".", backend: Optional[EventStoreBackend] = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        if backend:
            self.backend = backend
        else:
            self.backend = build_event_store_backend(repo_root=self.repo_root)
        self._subscribers: Dict[str, List[Callable[[SystemEvent], None]]] = defaultdict(list)
        self._session_subscribers: Dict[str, List[Callable[[SystemEvent], None]]] = defaultdict(list)
        self._session_seq: Dict[str, int] = defaultdict(int)
        self._subscriber_state: Dict[str, Dict[str, Any]] = {}
        self._subscriber_diag_cooldown_sec = 10.0
        try:
            self._subscriber_fail_threshold = max(
                1,
                int(str(os.getenv("QUENTIN_SUBSCRIBER_CIRCUIT_THRESHOLD", "3")).strip() or "3"),
            )
        except Exception:
            self._subscriber_fail_threshold = 3
        self._cursor_dir = self.repo_root / "data" / "system_events" / "cursors"
        self._cursor_dir.mkdir(parents=True, exist_ok=True)

    def _cursor_file(self, session_id: str) -> Path:
        return self._cursor_dir / f"{_safe_session_key(session_id)}.cursor"

    def subscribe(self, event_type: str, callback: Callable[[SystemEvent], None]):
        """
        Subscribe to a specific event type (e.g. 'physical_change').
        """
        self._subscribers[event_type].append(callback)

    def subscribe_session(self, session_id: str, callback: Callable[[BrainEvent], None]) -> None:
        sid = str(session_id or "global")
        if not callable(callback):
            return
        callback_id = f"session:{sid}:{uuid.uuid4().hex[:10]}"
        self._subscriber_state[callback_id] = {
            "session_id": sid,
            "callback_id": callback_id,
            "failures_total": 0,
            "consecutive_failures": 0,
            "opened_until": 0.0,
            "last_error": "",
            "last_event_type": "",
            "last_failure_at": "",
            "last_success_at": "",
            "last_diag_at": 0.0,
            "dropped_total": 0,
        }

        def _adapt(ev: SystemEvent) -> None:
            state = self._subscriber_state.get(callback_id) or {}
            now_ts = time.time()
            opened_until = float(state.get("opened_until") or 0.0)
            if opened_until > now_ts:
                state["dropped_total"] = int(state.get("dropped_total") or 0) + 1
                self._subscriber_state[callback_id] = state
                return
            try:
                callback(BrainEvent.from_system_event(ev))
                state["consecutive_failures"] = 0
                state["last_success_at"] = _utc_now()
                state["last_event_type"] = str(getattr(ev, "event_type", "") or "")
                self._subscriber_state[callback_id] = state
            except Exception as exc:
                state["failures_total"] = int(state.get("failures_total") or 0) + 1
                state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
                state["last_error"] = str(exc)[:400]
                state["last_event_type"] = str(getattr(ev, "event_type", "") or "")
                state["last_failure_at"] = _utc_now()
                threshold = max(1, int(self._subscriber_fail_threshold or 3))
                if int(state["consecutive_failures"]) >= threshold:
                    backoff = min(30.0, float(int(state["consecutive_failures"])) * 2.0)
                    state["opened_until"] = now_ts + backoff
                self._subscriber_state[callback_id] = state
                self._maybe_emit_subscriber_diagnostic(callback_id=callback_id)

        self._session_subscribers[sid].append(_adapt)

    def emit_brain_event(
        self,
        *,
        session_id: str,
        event_type: str,
        category: str,
        phase: str,
        source: str = "",
        payload: Optional[Dict[str, Any]] = None,
        turn_id: str = "",
    ) -> BrainEvent:
        sid = str(session_id or "global")
        if int(self._session_seq.get(sid) or 0) <= 0:
            try:
                existing = self.list_events(session_id=sid, limit=2000)
                max_seq = 0
                for raw in existing:
                    try:
                        be = BrainEvent.from_system_event(raw)
                    except Exception:
                        continue
                    max_seq = max(max_seq, int(be.seq or 0))
                if max_seq > 0:
                    self._session_seq[sid] = max_seq
            except Exception:
                pass
        self._session_seq[sid] = int(self._session_seq.get(sid) or 0) + 1
        event = BrainEvent(
            event_id=str(uuid.uuid4()),
            session_id=sid,
            event_type=str(event_type or "brain.event"),
            category=str(category or "system"),
            phase=str(phase or "event"),
            created_at=_utc_now(),
            source=str(source or ""),
            turn_id=str(turn_id or ""),
            seq=int(self._session_seq[sid]),
            cursor="",
            payload=dict(payload or {}),
            idempotency_key="",
        )
        event.cursor = f"{int(event.seq)}:{event.event_id}"
        if not str(event.idempotency_key or "").strip():
            event.idempotency_key = str(event.event_id or "")
        self.enqueue_event(
            session_id=sid,
            event_type=event.event_type,
            payload=event.to_system_event_payload(),
            source=event.source,
        )
        return event

    def enqueue_event(
        self,
        *,
        session_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> SystemEvent:
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            session_id=str(session_id or "global"),
            event_type=str(event_type or "system_event"),
            created_at=_utc_now(),
            source=str(source or ""),
            payload=payload or {},
        )
        self.backend.enqueue_event(event.to_dict())
        
        # Broadcast (fail-closed): exact-type, wildcard, session-scoped.
        callbacks: List[Callable[[SystemEvent], None]] = []
        callbacks.extend(list(self._subscribers.get(str(event_type), [])))
        callbacks.extend(list(self._subscribers.get("*", [])))
        callbacks.extend(list(self._session_subscribers.get(str(event.session_id or "global"), [])))
        callbacks.extend(list(self._session_subscribers.get("*", [])))
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                continue
                    
        return event

    def _maybe_emit_subscriber_diagnostic(self, *, callback_id: str) -> None:
        state = self._subscriber_state.get(callback_id)
        if not isinstance(state, dict):
            return
        now_ts = time.time()
        last_diag = float(state.get("last_diag_at") or 0.0)
        cooldown = max(1.0, float(self._subscriber_diag_cooldown_sec or 10.0))
        if (now_ts - last_diag) < cooldown:
            return
        state["last_diag_at"] = now_ts
        self._subscriber_state[callback_id] = state
        try:
            self.emit_brain_event(
                session_id=str(state.get("session_id") or "global"),
                event_type="subscriber_diagnostic",
                category="gateway",
                phase="update",
                source="system_event_queue",
                payload={
                    "callback_id": str(state.get("callback_id") or callback_id),
                    "failures_total": int(state.get("failures_total") or 0),
                    "consecutive_failures": int(state.get("consecutive_failures") or 0),
                    "opened_until": float(state.get("opened_until") or 0.0),
                    "is_circuit_open": float(state.get("opened_until") or 0.0) > time.time(),
                    "dropped_total": int(state.get("dropped_total") or 0),
                    "last_event_type": str(state.get("last_event_type") or ""),
                    "last_error": str(state.get("last_error") or ""),
                },
                turn_id="",
            )
        except Exception:
            pass

    def get_subscriber_stats(self, *, session_id: str = "") -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        sid = str(session_id or "").strip()
        for state in list(self._subscriber_state.values()):
            if not isinstance(state, dict):
                continue
            if sid and str(state.get("session_id") or "") != sid:
                continue
            out.append(
                {
                    "session_id": str(state.get("session_id") or ""),
                    "callback_id": str(state.get("callback_id") or ""),
                    "failures_total": int(state.get("failures_total") or 0),
                    "consecutive_failures": int(state.get("consecutive_failures") or 0),
                    "opened_until": float(state.get("opened_until") or 0.0),
                    "is_circuit_open": float(state.get("opened_until") or 0.0) > time.time(),
                    "dropped_total": int(state.get("dropped_total") or 0),
                    "last_event_type": str(state.get("last_event_type") or ""),
                    "last_error": str(state.get("last_error") or ""),
                    "last_failure_at": str(state.get("last_failure_at") or ""),
                    "last_success_at": str(state.get("last_success_at") or ""),
                }
            )
        return out

    def drain_events(self, *, session_id: str, limit: int = 20) -> List[SystemEvent]:
        raw_events = self.backend.drain_events(session_id=session_id, limit=limit)
        return [SystemEvent.from_dict(e) for e in raw_events]

    def get_acked_cursor(self, *, session_id: str) -> str:
        path = self._cursor_file(session_id)
        if not path.exists():
            return ""
        lock = acquire_session_write_lock(session_file=path)
        try:
            return str(path.read_text(encoding="utf-8", errors="ignore") or "").strip()
        finally:
            lock["release"]()

    def ack_cursor(self, *, session_id: str, cursor: str) -> str:
        value = str(cursor or "").strip()
        if not value:
            return self.get_acked_cursor(session_id=session_id)
        path = self._cursor_file(session_id)
        lock = acquire_session_write_lock(session_file=path)
        try:
            current = ""
            if path.exists():
                current = str(path.read_text(encoding="utf-8", errors="ignore") or "").strip()
            current_idx = self._cursor_index(current)
            incoming_idx = self._cursor_index(value)
            if incoming_idx > current_idx or (incoming_idx == current_idx and value > current):
                path.write_text(value, encoding="utf-8")
                return value
            return current
        finally:
            lock["release"]()

    def consume_pending(self, session_id: str = "global") -> List[SystemEvent]:
        """
        P5: Compatibility alias for drain_events.
        """
        return self.drain_events(session_id=session_id)

    @staticmethod
    def _cursor_index(value: str) -> int:
        try:
            return int(str(value or "").split(":", 1)[0])
        except Exception:
            return 0

    def _filter_after_cursor(self, events: List[BrainEvent], *, after_cursor: str) -> List[BrainEvent]:
        needle = str(after_cursor or "").strip()
        if not needle:
            return events
        out: List[BrainEvent] = []
        after_idx = self._cursor_index(needle)
        for event in events:
            cur = str(event.cursor or f"{int(event.seq)}:{event.event_id}")
            idx = self._cursor_index(cur)
            if idx > after_idx:
                out.append(event)
            elif idx == after_idx and cur > needle:
                out.append(event)
        return out

    @staticmethod
    def _dedupe_by_idempotency(events: List[BrainEvent]) -> List[BrainEvent]:
        seen: set[str] = set()
        out: List[BrainEvent] = []
        for event in events:
            key = str(event.idempotency_key or event.event_id or "")
            if not key:
                out.append(event)
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(event)
        return out

    def list_brain_events(
        self,
        *,
        session_id: str,
        limit: int = 50,
        after_cursor: str = "",
        dedupe: bool = True,
    ) -> List[BrainEvent]:
        listed = self.list_events(session_id=session_id, limit=max(limit, 200) if after_cursor else limit)
        out: List[BrainEvent] = []
        for event in listed:
            try:
                be = BrainEvent.from_system_event(event)
                if not be.cursor:
                    be.cursor = f"{int(be.seq)}:{be.event_id}"
                out.append(be)
            except Exception:
                continue
        filtered = self._filter_after_cursor(out, after_cursor=after_cursor)
        if dedupe:
            filtered = self._dedupe_by_idempotency(filtered)
        return filtered[: max(1, int(limit))]

    def drain_brain_events(
        self,
        *,
        session_id: str,
        limit: int = 50,
        after_cursor: str = "",
        dedupe: bool = True,
    ) -> List[BrainEvent]:
        if str(after_cursor or "").strip():
            return self.list_brain_events(session_id=session_id, limit=limit, after_cursor=after_cursor, dedupe=dedupe)
        drained = self.drain_events(session_id=session_id, limit=limit)
        out: List[BrainEvent] = []
        for event in drained:
            try:
                be = BrainEvent.from_system_event(event)
                if not be.cursor:
                    be.cursor = f"{int(be.seq)}:{be.event_id}"
                out.append(be)
            except Exception:
                continue
        if dedupe:
            out = self._dedupe_by_idempotency(out)
        return out

    def list_events(self, *, session_id: str, limit: int = 20) -> List[SystemEvent]:
        raw_events = self.backend.peek_events(session_id=session_id, limit=limit)
        return [SystemEvent.from_dict(e) for e in raw_events]

    def format_for_prompt(self, session_id: str = "global", *, limit: int = 20, max_chars: int = 2400) -> str:
        """
        Backwards-compatible helper used by prompt building code.

        Note: This does not drain events; it only formats a peek.
        """
        events = self.list_events(session_id=session_id, limit=limit)
        return self.format_events_for_prompt(events, max_chars=max_chars)

    @staticmethod
    def format_events_for_prompt(events: List[SystemEvent], *, max_chars: int = 2400) -> str:
        if not events:
            return ""
        lines = [
            "System events completed in background. Review and reflect them in your next response when relevant:"
        ]
        for e in events:
            payload = e.payload or {}
            summary_bits = [f"type={e.event_type}"]
            if e.source:
                summary_bits.append(f"source={e.source}")
            for k in ("gap_id", "patch_id", "status", "reason", "message", "runtime_mode"):
                v = payload.get(k)
                if v is not None and str(v).strip():
                    summary_bits.append(f"{k}={str(v).strip()}")
            guardrail_remaining = payload.get("guardrail_remaining_sec")
            if guardrail_remaining is not None:
                try:
                    summary_bits.append(f"guardrail_remaining_sec={float(guardrail_remaining):.1f}")
                except Exception:
                    pass
            lines.append("- " + " | ".join(summary_bits))
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[: max(0, max_chars - 3)] + "..."
        return text


def normalize_background_event(event: SystemEvent) -> Dict[str, Any]:
    payload = event.payload or {}
    status = str(payload.get("status") or payload.get("task_status") or "").strip().lower()
    if not status and event.event_type in BACKGROUND_TASK_EVENT_TYPES:
        status = event.event_type.replace("background_task_", "")
    if status not in {"started", "completed", "failed", "cancelled", "timeout"}:
        status = "unknown"
    task_id = str(payload.get("task_id") or payload.get("gap_id") or payload.get("patch_id") or "").strip()
    return {
        "event_id": event.event_id,
        "session_id": event.session_id,
        "created_at": event.created_at,
        "source": event.source,
        "event_type": event.event_type,
        "status": status,
        "task_id": task_id,
        "payload": payload,
    }

# P5: Global singleton
system_events = SystemEventQueue()


def subscribe_session(session_id: str, callback: Callable[[BrainEvent], None], *, queue: Optional[SystemEventQueue] = None) -> None:
    target = queue or system_events
    target.subscribe_session(session_id=session_id, callback=callback)


def drain_events(
    session_id: str,
    *,
    limit: int = 50,
    after_cursor: str = "",
    dedupe: bool = True,
    queue: Optional[SystemEventQueue] = None,
) -> List[BrainEvent]:
    target = queue or system_events
    return target.drain_brain_events(session_id=session_id, limit=limit, after_cursor=after_cursor, dedupe=dedupe)


def ack_cursor(session_id: str, cursor: str, *, queue: Optional[SystemEventQueue] = None) -> str:
    target = queue or system_events
    return target.ack_cursor(session_id=session_id, cursor=cursor)
