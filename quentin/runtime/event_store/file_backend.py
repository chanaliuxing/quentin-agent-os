from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from quentin.runtime.event_store.base import EventStoreBackend
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.utils.time import now_utc_iso


def _utc_now() -> str:
    return now_utc_iso()


def _safe_session_key(session_id: str) -> str:
    raw = str(session_id or "").strip() or "global"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)
    return cleaned or "global"


class FileEventStoreBackend:
    """
    Lightweight per-session event queue persisted as JSONL files.
    Default implementation for P2-C.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        root = Path(repo_root).resolve()
        self._dir = root / "data" / "system_events"
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def id(self) -> str:
        return "file"

    def _session_file(self, session_id: str) -> Path:
        return self._dir / f"{_safe_session_key(session_id)}.jsonl"

    def enqueue_event(self, event: Dict[str, Any]) -> None:
        session_id = str(event.get("session_id") or "global")
        # Ensure ID and Timestamp
        if "event_id" not in event:
            event["event_id"] = str(uuid.uuid4())
        if "created_at" not in event:
            event["created_at"] = _utc_now()
            
        path = self._session_file(session_id)
        lock = acquire_session_write_lock(session_file=path)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

    def drain_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        path = self._session_file(session_id)
        if not path.exists():
            return []

        lock = acquire_session_write_lock(session_file=path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            events: List[Dict[str, Any]] = []
            remaining: List[str] = []
            for line in lines:
                raw = (line or "").strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if len(events) < max(1, int(limit)):
                    events.append(obj)
                else:
                    remaining.append(raw)
            if remaining:
                path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
            return events
        finally:
            lock["release"]()

    def peek_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        path = self._session_file(session_id)
        if not path.exists():
            return []
        lock = acquire_session_write_lock(session_file=path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            events: List[Dict[str, Any]] = []
            for line in lines:
                raw = (line or "").strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if len(events) >= max(1, int(limit)):
                    break
                events.append(obj)
            return events
        finally:
            lock["release"]()

    def list_sessions(self) -> List[str]:
        # List all .jsonl files in the dir
        if not self._dir.exists():
            return []
        return [p.stem for p in self._dir.glob("*.jsonl")]
