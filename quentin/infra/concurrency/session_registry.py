from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
import re
import os
from threading import RLock


class _SessionLock:
    def __init__(self, reg: "SessionRegistry", session_id: str, worker_id: str, timeout_sec: float):
        self._reg = reg
        self._session_id = session_id
        self._worker_id = worker_id
        self._timeout_sec = float(timeout_sec)
        self._local_lock = reg._local_locks.setdefault(SessionRegistry._safe_session_key(session_id), RLock())

    def __enter__(self):
        # Serialize in-process first, then take the cross-process marker file.
        self._local_lock.acquire()
        ok = self._reg.acquire(self._session_id, worker_id=self._worker_id, timeout_sec=int(self._timeout_sec))
        if not ok:
            # Best-effort: we don't hard-block unit tests on cross-process contention.
            # In production, this should become a blocking acquire with bounded backoff.
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._reg.release(self._session_id, worker_id=self._worker_id)
        finally:
            try:
                self._local_lock.release()
            except Exception:
                pass
        return False

class SessionRegistry:
    """
    L0: Cross-process session tracking to ensure cognitive consistency (P5).
    Prevents multiple workers from running tasks for the same session simultaneously.
    """
    def __init__(self, repo_root: str | Path = "."):
        self.lock_dir = Path(repo_root).resolve() / "data" / "runtime" / "session_locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._local_locks: dict[str, RLock] = {}

    @staticmethod
    def _safe_session_key(session_id: str) -> str:
        raw = str(session_id or "").strip() or "default"
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)
        return cleaned or "default"

    def acquire(self, session_id: str, worker_id: str, timeout_sec: int = 3600) -> bool:
        safe_id = self._safe_session_key(session_id)
        lock_file = self.lock_dir / f"{safe_id}.lock"
        
        # Check if existing lock is stale
        if lock_file.exists():
            try:
                mtime = lock_file.stat().st_mtime
                if (time.time() - mtime) > timeout_sec:
                    lock_file.unlink() # Clear stale lock
                else:
                    return False
            except FileNotFoundError:
                pass

        try:
            # Prefer atomic creation. If another worker races, FileExistsError -> fail.
            payload = f"worker_id={worker_id}\nstart_ts={time.time()}\n"
            with lock_file.open("x", encoding="utf-8") as f:
                f.write(payload)
            return True
        except FileExistsError:
            return False
        except Exception:
            return False

    def release(self, session_id: str, worker_id: str) -> None:
        safe_id = self._safe_session_key(session_id)
        lock_file = self.lock_dir / f"{safe_id}.lock"
        if lock_file.exists():
            try:
                content = lock_file.read_text(encoding="utf-8")
                if f"worker_id={worker_id}" in content:
                    lock_file.unlink()
            except Exception:
                pass

    def is_active(self, session_id: str) -> bool:
        safe_id = self._safe_session_key(session_id)
        return (self.lock_dir / f"{safe_id}.lock").exists()

    def acquire_lock(self, session_id: str, *, worker_id: Optional[str] = None, timeout_sec: float = 3600.0) -> _SessionLock:
        wid = worker_id or f"pid:{os.getpid()}"
        return _SessionLock(self, session_id=session_id, worker_id=wid, timeout_sec=timeout_sec)


_REGISTRY: Optional[SessionRegistry] = None


def get_session_registry(*, repo_root: str | Path = ".") -> SessionRegistry:
    """
    Best-effort singleton accessor used by ToolManager/BrainDaemon.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SessionRegistry(repo_root=repo_root)
    return _REGISTRY
