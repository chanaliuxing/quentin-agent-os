from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from quentin.memory.models import MemoryQuery


@dataclass
class MemoryManagerConfig:
    sync_on_session_start: bool = True
    sync_on_search: bool = True
    periodic_sync_enabled: bool = False
    periodic_sync_interval_s: float = 60.0
    memory_sync_force: bool = False
    memory_sync_concurrency: int = 0


class MemoryManager:
    """
    Lifecycle orchestrator aligned with OpenClaw manager.ts responsibilities:
    - startup/session-start sync
    - pre-search sync gate
    - periodic background sync
    - stable status/health surface
    """

    def __init__(
        self,
        *,
        memory_fabric: Any,
        repo_root: str | Path = ".",
        config: Optional[MemoryManagerConfig] = None,
    ) -> None:
        self.memory_fabric = memory_fabric
        self.repo_root = Path(repo_root).resolve()
        self.config = config or MemoryManagerConfig()
        self._session_transcripts: Dict[str, Set[str]] = {}
        self._last_sync_at: Optional[float] = None
        self._last_sync_result: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register_session_transcript(self, *, session_id: str, transcript_path: str | Path) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        p = str(Path(transcript_path).resolve())
        with self._lock:
            self._session_transcripts.setdefault(sid, set()).add(p)

    def list_session_transcripts(self, *, session_id: Optional[str] = None) -> Dict[str, List[str]]:
        with self._lock:
            if session_id is not None:
                sid = str(session_id or "")
                return {sid: sorted(self._session_transcripts.get(sid, set()))}
            return {sid: sorted(paths) for sid, paths in self._session_transcripts.items()}

    def run_sync_cycle(self, *, force: Optional[bool] = None, dirty_files: Optional[Set[str]] = None) -> Dict[str, Any]:
        force_v = bool(self.config.memory_sync_force if force is None else force)
        sync_res = self.memory_fabric.sync_memory_files(
            workspace_dir=self.repo_root,
            force=force_v,
            dirty_files=dirty_files,
            concurrency=int(self.config.memory_sync_concurrency or 0),
        )

        session_sync: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            session_paths = {sid: list(paths) for sid, paths in self._session_transcripts.items()}
        for sid, paths in session_paths.items():
            per: Dict[str, Any] = {"indexed": 0, "advanced": 0, "noop": 0, "errors": 0}
            for p in paths:
                try:
                    out = self.memory_fabric.sync_session_file_delta(p)
                    st = str(out.get("status") or "noop")
                    if st in per:
                        per[st] += 1
                    else:
                        per["noop"] += 1
                except Exception:
                    per["errors"] += 1
            session_sync[sid] = per

        result = {"memory_files": sync_res, "session_files": session_sync}
        with self._lock:
            self._last_sync_at = time.time()
            self._last_sync_result = result
            self._last_error = None
        return result

    def on_session_start(self, *, session_id: str, transcript_path: Optional[str | Path] = None) -> Dict[str, Any]:
        if transcript_path is not None:
            self.register_session_transcript(session_id=session_id, transcript_path=transcript_path)
        if not self.config.sync_on_session_start:
            return {"status": "skipped"}
        return self.run_sync_cycle(force=False)

    def maybe_sync_before_search(self, *, query: Optional[MemoryQuery] = None) -> Dict[str, Any]:
        _ = query
        if not self.config.sync_on_search:
            return {"status": "skipped"}
        return self.run_sync_cycle(force=False)

    def start_periodic_sync(self) -> bool:
        if not self.config.periodic_sync_enabled:
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._periodic_worker, daemon=True)
            self._thread.start()
            return True

    def stop_periodic_sync(self) -> None:
        self._stop_evt.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=1.0)

    def _periodic_worker(self) -> None:
        interval = max(1.0, float(self.config.periodic_sync_interval_s or 60.0))
        while not self._stop_evt.wait(interval):
            try:
                self.run_sync_cycle(force=False)
            except Exception as e:
                with self._lock:
                    self._last_error = str(e)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "config": {
                    "sync_on_session_start": bool(self.config.sync_on_session_start),
                    "sync_on_search": bool(self.config.sync_on_search),
                    "periodic_sync_enabled": bool(self.config.periodic_sync_enabled),
                    "periodic_sync_interval_s": float(self.config.periodic_sync_interval_s),
                    "memory_sync_force": bool(self.config.memory_sync_force),
                    "memory_sync_concurrency": int(self.config.memory_sync_concurrency or 0),
                },
                "sessions": {sid: sorted(paths) for sid, paths in self._session_transcripts.items()},
                "last_sync_at": self._last_sync_at,
                "last_sync_result": dict(self._last_sync_result or {}),
                "last_error": self._last_error,
                "periodic_running": bool(self._thread is not None and self._thread.is_alive()),
            }
