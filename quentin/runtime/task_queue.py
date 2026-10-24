from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import uuid

from quentin.runtime.session_write_lock import acquire_session_write_lock


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TaskQueueItem:
    task_id: str
    input_text: str
    domain: str = "core"
    environment: str = "sandbox"
    session_id: str = ""
    priority: int = 0
    metadata: Dict[str, Any] = None  # type: ignore[assignment]
    status: str = "pending"  # pending | claimed | done | failed
    created_at: str = ""
    claimed_at: str = ""
    finished_at: str = ""
    worker_id: str = ""
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("metadata") is None:
            d["metadata"] = {}
        return d

    @classmethod
    def new(
        cls,
        *,
        input_text: str,
        domain: str = "core",
        environment: str = "sandbox",
        session_id: str = "",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TaskQueueItem":
        return cls(
            task_id=f"qtask::{uuid.uuid4().hex}",
            input_text=str(input_text or ""),
            domain=str(domain or "core"),
            environment=str(environment or "sandbox"),
            session_id=str(session_id or ""),
            priority=int(priority or 0),
            metadata=dict(metadata or {}),
            status="pending",
            created_at=_now_iso(),
        )


class TaskQueue:
    """
    Simple file-backed queue (JSONL).

    This intentionally favors robustness and debuggability over throughput:
    - All state is persisted in one JSONL file.
    - Updates rewrite the file under a write lock.
    """

    def __init__(self, *, repo_root: str | Path = ".", path: str | Path = "data/tasks/queue.jsonl") -> None:
        self.repo_root = Path(repo_root).resolve()
        override = (os.getenv("QUENTIN_TASK_QUEUE_PATH") or "").strip()
        if override:
            p = Path(override).expanduser()
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            self.path = p
        else:
            self.path = (self.repo_root / path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item: TaskQueueItem) -> None:
        lock = acquire_session_write_lock(session_file=self.path)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

    def load_all(self, *, limit: Optional[int] = None) -> List[TaskQueueItem]:
        if not self.path.exists():
            return []
        out: List[TaskQueueItem] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                out.append(self._coerce_item(raw))
        if limit is not None and limit > 0:
            return out[-limit:]
        return out

    def _rewrite_all(self, items: List[TaskQueueItem]) -> None:
        lock = acquire_session_write_lock(session_file=self.path)
        try:
            with self.path.open("w", encoding="utf-8") as f:
                for it in items:
                    f.write(json.dumps(it.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

    def claim_next(self, *, worker_id: str, only_domain: str = "", only_environment: str = "", limit_scan: int = 5000) -> Optional[TaskQueueItem]:
        items = self.load_all(limit=limit_scan)
        if not items:
            return None

        def _eligible(it: TaskQueueItem) -> bool:
            if it.status != "pending":
                return False
            if only_domain and it.domain != only_domain:
                return False
            if only_environment and it.environment != only_environment:
                return False
            return True

        pending = [it for it in items if _eligible(it)]
        if not pending:
            return None

        # Higher priority first, then FIFO.
        pending.sort(key=lambda x: (-int(x.priority or 0), x.created_at or ""))
        target_id = pending[0].task_id
        for it in items:
            if it.task_id == target_id:
                it.status = "claimed"
                it.claimed_at = _now_iso()
                it.worker_id = worker_id
                self._rewrite_all(items)
                return it
        return None

    def claim_by_id(self, *, task_id: str, worker_id: str, limit_scan: int = 5000) -> Optional[TaskQueueItem]:
        """
        Claim a specific pending task atomically.
        Returns None if task not found or not pending.
        """
        target = str(task_id or "").strip()
        if not target:
            return None
        items = self.load_all(limit=limit_scan)
        if not items:
            return None
        for it in items:
            if it.task_id != target:
                continue
            if it.status != "pending":
                return None
            it.status = "claimed"
            it.claimed_at = _now_iso()
            it.worker_id = worker_id
            self._rewrite_all(items)
            return it
        return None

    def mark_done(self, task_id: str, *, ok: bool, error: str = "") -> None:
        items = self.load_all(limit=5000)
        changed = False
        for it in items:
            if it.task_id != task_id:
                continue
            it.status = "done" if ok else "failed"
            it.finished_at = _now_iso()
            it.last_error = str(error or "")
            changed = True
            break
        if changed:
            self._rewrite_all(items)

    @staticmethod
    def _coerce_item(raw: Dict[str, Any]) -> TaskQueueItem:
        return TaskQueueItem(
            task_id=str(raw.get("task_id") or raw.get("id") or ""),
            input_text=str(raw.get("input_text") or raw.get("text") or ""),
            domain=str(raw.get("domain") or "core"),
            environment=str(raw.get("environment") or "sandbox"),
            session_id=str(raw.get("session_id") or ""),
            priority=int(raw.get("priority") or 0),
            metadata=dict(raw.get("metadata") or {}),
            status=str(raw.get("status") or "pending"),
            created_at=str(raw.get("created_at") or ""),
            claimed_at=str(raw.get("claimed_at") or ""),
            finished_at=str(raw.get("finished_at") or ""),
            worker_id=str(raw.get("worker_id") or ""),
            last_error=str(raw.get("last_error") or ""),
        )
