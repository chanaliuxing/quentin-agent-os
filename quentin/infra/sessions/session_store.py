from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from quentin.infra.concurrency.abort_signal import abort_registry
from quentin.infra.concurrency.lanes import resolve_session_lane
from quentin.infra.concurrency.session_registry import get_session_registry


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_session_key(session_id: str) -> str:
    raw = str(session_id or "").strip() or "default"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)
    return cleaned or "default"


@dataclass
class SessionCompactionState:
    compaction_count: int = 0
    last_compacted_at: str = ""
    last_reason: str = ""
    last_summary: str = ""


@dataclass
class SessionState:
    session_id: str
    lane_key: str
    lock_key: str
    abort_signal_id: str
    history: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    compaction: SessionCompactionState = field(default_factory=SessionCompactionState)
    dirty_flags: Dict[str, bool] = field(default_factory=dict)
    deltas_cursor: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: str = field(default_factory=_utc_iso)
    updated_at: str = field(default_factory=_utc_iso)

    @classmethod
    def new(cls, session_id: str, *, metadata: Optional[Dict[str, Any]] = None) -> "SessionState":
        sid = str(session_id or "").strip() or "default"
        lane = resolve_session_lane(sid)
        return cls(
            session_id=sid,
            lane_key=lane,
            lock_key=lane,
            abort_signal_id=sid,
            metadata=dict(metadata or {}),
        )

    def touch(self) -> None:
        self.version = max(1, int(self.version)) + 1
        self.updated_at = _utc_iso()


@dataclass
class CompactionReport:
    compacted: bool
    reason: str
    before_count: int
    after_count: int
    before_chars: int
    after_chars: int


class SessionPolicy:
    """
    Deterministic history trimming and compaction policy.
    """

    def __init__(
        self,
        *,
        max_history_messages: Optional[int] = None,
        max_history_chars: Optional[int] = None,
        keep_recent_messages: Optional[int] = None,
        summary_max_chars: Optional[int] = None,
        min_messages_to_compact: Optional[int] = None,
    ) -> None:
        resolved_max_messages = max_history_messages if max_history_messages is not None else os.getenv("QUENTIN_SESSION_HISTORY_MAX_MESSAGES", "80")
        resolved_max_chars = max_history_chars if max_history_chars is not None else os.getenv("QUENTIN_SESSION_HISTORY_MAX_CHARS", "48000")
        resolved_keep_recent = keep_recent_messages if keep_recent_messages is not None else os.getenv("QUENTIN_SESSION_HISTORY_KEEP_RECENT", "20")
        resolved_summary_chars = summary_max_chars if summary_max_chars is not None else os.getenv("QUENTIN_SESSION_COMPACTION_SUMMARY_MAX_CHARS", "1200")
        resolved_min_compact = min_messages_to_compact if min_messages_to_compact is not None else os.getenv("QUENTIN_SESSION_COMPACTION_MIN_MESSAGES", "8")
        self.max_history_messages = max(1, int(resolved_max_messages or 80))
        self.max_history_chars = max(100, int(resolved_max_chars or 48000))
        self.keep_recent_messages = max(1, int(resolved_keep_recent or 20))
        self.summary_max_chars = max(64, int(resolved_summary_chars or 1200))
        self.min_messages_to_compact = max(2, int(resolved_min_compact or 8))

    def _total_chars(self, history: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in history:
            total += len(str(msg.get("content") or ""))
        return total

    def should_compact(self, state: SessionState) -> tuple[bool, str]:
        history = state.history or []
        if len(history) < self.min_messages_to_compact:
            return False, "too_few_messages"
        if len(history) > self.max_history_messages:
            return True, "messages_overflow"
        if self._total_chars(history) > self.max_history_chars:
            return True, "chars_overflow"
        return False, "within_budget"

    def _summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        summarizer: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ) -> str:
        if summarizer is not None:
            text = str(summarizer(messages) or "").strip()
            if text:
                return text[: self.summary_max_chars]

        # Deterministic fallback summary for predictable tests and robust runtime behavior.
        lines: List[str] = []
        for msg in messages[-64:]:
            role = str(msg.get("role") or "unknown")
            content = str(msg.get("content") or "").replace("\n", " ").strip()
            if content:
                lines.append(f"[{role}] {content[:140]}")
        summary = " ; ".join(lines)
        if not summary:
            summary = "Session history compacted with no significant textual payload."
        return summary[: self.summary_max_chars]

    def maybe_compact(
        self,
        state: SessionState,
        *,
        summarizer: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ) -> CompactionReport:
        history = list(state.history or [])
        before_count = len(history)
        before_chars = self._total_chars(history)
        should, reason = self.should_compact(state)
        if not should:
            return CompactionReport(
                compacted=False,
                reason=reason,
                before_count=before_count,
                after_count=before_count,
                before_chars=before_chars,
                after_chars=before_chars,
            )

        keep_n = min(len(history), self.keep_recent_messages)
        head = history[:-keep_n]
        tail = history[-keep_n:]
        gist = self._summarize_messages(head, summarizer=summarizer)
        gist_message = {
            "role": "system",
            "content": f"[[SESSION_COMPACTION_GIST]] {gist}",
            "metadata": {
                "session_compaction": True,
                "source": "session_policy",
                "reason": reason,
            },
        }

        state.summary = gist
        state.history = [gist_message] + tail
        state.compaction.compaction_count = int(state.compaction.compaction_count) + 1
        state.compaction.last_compacted_at = _utc_iso()
        state.compaction.last_reason = reason
        state.compaction.last_summary = gist
        state.dirty_flags["history"] = True
        state.dirty_flags["compaction"] = True
        state.touch()

        after_chars = self._total_chars(state.history)
        return CompactionReport(
            compacted=True,
            reason=reason,
            before_count=before_count,
            after_count=len(state.history),
            before_chars=before_chars,
            after_chars=after_chars,
        )


class SessionStore:
    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        raw_enabled = str(os.getenv("QUENTIN_SESSION_STORE_ENABLED", "1") or "").strip().lower()
        self.enabled = raw_enabled in {"1", "true", "yes", "on"}
        configured_dir = str(os.getenv("QUENTIN_SESSION_STORE_DIR", "data/runtime/sessions") or "data/runtime/sessions").strip()
        self.base_dir = (self.repo_root / configured_dir).resolve() if not Path(configured_dir).is_absolute() else Path(configured_dir).resolve()
        if self.enabled:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        self._registry = get_session_registry(repo_root=self.repo_root)
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._memory_fallback: Dict[str, SessionState] = {}

    def _state_path(self, session_id: str) -> Path:
        return self.base_dir / f"{_safe_session_key(session_id)}.json"

    def _get_lock(self, session_id: str) -> threading.Lock:
        key = _safe_session_key(session_id)
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def _serialize(self, state: SessionState) -> Dict[str, Any]:
        payload = asdict(state)
        payload["compaction"] = asdict(state.compaction)
        return payload

    def _deserialize(self, data: Dict[str, Any], *, session_id: str) -> SessionState:
        compaction_raw = data.get("compaction") if isinstance(data.get("compaction"), dict) else {}
        compaction = SessionCompactionState(
            compaction_count=int(compaction_raw.get("compaction_count", 0) or 0),
            last_compacted_at=str(compaction_raw.get("last_compacted_at") or ""),
            last_reason=str(compaction_raw.get("last_reason") or ""),
            last_summary=str(compaction_raw.get("last_summary") or ""),
        )
        return SessionState(
            session_id=str(data.get("session_id") or session_id),
            lane_key=str(data.get("lane_key") or resolve_session_lane(session_id)),
            lock_key=str(data.get("lock_key") or resolve_session_lane(session_id)),
            abort_signal_id=str(data.get("abort_signal_id") or session_id),
            history=list(data.get("history") or []),
            summary=str(data.get("summary") or ""),
            compaction=compaction,
            dirty_flags=dict(data.get("dirty_flags") or {}),
            deltas_cursor={k: int(v) for k, v in dict(data.get("deltas_cursor") or {}).items() if isinstance(v, int) or str(v).isdigit()},
            metadata=dict(data.get("metadata") or {}),
            version=max(1, int(data.get("version", 1) or 1)),
            created_at=str(data.get("created_at") or _utc_iso()),
            updated_at=str(data.get("updated_at") or _utc_iso()),
        )

    def load(self, session_id: str) -> SessionState:
        if not self.enabled:
            return self._memory_fallback.get(str(session_id), SessionState.new(session_id))
        path = self._state_path(session_id)
        if not path.exists():
            return SessionState.new(session_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return SessionState.new(session_id)
        if not isinstance(raw, dict):
            return SessionState.new(session_id)
        state = self._deserialize(raw, session_id=session_id)
        # Keep concurrency handles coherent with current session_id.
        state.lane_key = resolve_session_lane(state.session_id)
        if not state.lock_key:
            state.lock_key = state.lane_key
        if not state.abort_signal_id:
            state.abort_signal_id = state.session_id
        return state

    def save(self, state: SessionState, *, expected_version: Optional[int] = None) -> SessionState:
        if not self.enabled:
            if expected_version is not None:
                cur = self._memory_fallback.get(state.session_id)
                cur_ver = int(cur.version) if cur is not None else 1
                if cur_ver != int(expected_version):
                    raise RuntimeError(
                        f"Session version conflict for {state.session_id}: expected={expected_version} actual={cur_ver}"
                    )
                state.version = int(expected_version) + 1
            self._memory_fallback[state.session_id] = state
            return state
        lock = self._get_lock(state.session_id)
        with lock:
            path = self._state_path(state.session_id)
            if expected_version is not None and path.exists():
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    current = {}
                if isinstance(current, dict):
                    cur_ver = int(current.get("version", 1) or 1)
                    if cur_ver != int(expected_version):
                        raise RuntimeError(
                            f"Session version conflict for {state.session_id}: expected={expected_version} actual={cur_ver}"
                        )

            state.updated_at = _utc_iso()
            if expected_version is not None:
                state.version = int(expected_version) + 1
            else:
                state.version = max(1, int(state.version or 1))

            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._serialize(state), ensure_ascii=False, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
        return state

    def load_or_create(self, session_id: str, *, metadata: Optional[Dict[str, Any]] = None) -> SessionState:
        state = self.load(session_id)
        if metadata:
            for k, v in metadata.items():
                if k not in state.metadata:
                    state.metadata[k] = v
        # Touch abort registry to ensure signal exists for this session model.
        abort_registry.get_signal(state.abort_signal_id)
        return state

    def append_history(self, session_id: str, message: Dict[str, Any]) -> SessionState:
        state = self.load_or_create(session_id)
        state.history.append(dict(message or {}))
        state.dirty_flags["history"] = True
        state.touch()
        return self.save(state)

    def maybe_compact(
        self,
        session_id: str,
        *,
        policy: Optional[SessionPolicy] = None,
        summarizer: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ) -> tuple[SessionState, CompactionReport]:
        state = self.load_or_create(session_id)
        active_policy = policy or SessionPolicy()
        report = active_policy.maybe_compact(state, summarizer=summarizer)
        if report.compacted:
            state = self.save(state)
        return state, report

    def state_file_path(self, session_id: str) -> Path:
        return self._state_path(session_id)

    def acquire_lock(self, state: SessionState, *, worker_id: Optional[str] = None, timeout_sec: float = 3600.0) -> Any:
        lock_key = str(getattr(state, "lock_key", "") or state.session_id)
        return self._registry.acquire_lock(lock_key, worker_id=worker_id, timeout_sec=timeout_sec)
