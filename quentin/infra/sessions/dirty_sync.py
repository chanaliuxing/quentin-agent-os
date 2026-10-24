from __future__ import annotations

import hashlib
import json
import time
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Set

logger = logging.getLogger(__name__)

class DirtySyncManager:
    """
    P5: Ported from OpenClaw's dirty sync and session-delta logic.
    Manages debounced synchronization of session state to memory fabric.
    """
    def __init__(
        self,
        sync_callback: Callable[[str, Dict[str, Any]], None],
        debounce_sec: float = 5.0,
        dedupe_ttl_sec: float = 120.0,
    ):
        self.sync_callback = sync_callback
        self.debounce_sec = debounce_sec
        self.dedupe_ttl_sec = dedupe_ttl_sec
        self._pending_data: Dict[str, Dict[str, Any]] = {}
        self._last_trigger: Dict[str, float] = {}
        self._timers: Dict[str, threading.Timer] = {}
        self._recent_fingerprints: Dict[str, float] = {}
        self._inflight_fingerprints: Set[str] = set()
        self._dropped_malformed: int = 0
        self._lock = threading.Lock()

    def track_change(self, session_id: str, data_delta: Dict[str, Any]):
        """
        Records a change and schedules a debounced sync.
        """
        normalized = self._normalize_delta(data_delta)
        if normalized is None:
            with self._lock:
                self._dropped_malformed += 1
            return
        with self._lock:
            if session_id not in self._pending_data:
                self._pending_data[session_id] = {}
            
            # Merge delta
            self._pending_data[session_id].update(normalized)
            
            # Cancel existing timer
            if session_id in self._timers:
                self._timers[session_id].cancel()
            
            # Schedule new timer
            t = threading.Timer(self.debounce_sec, self._do_sync, args=[session_id])
            self._timers[session_id] = t
            t.start()
            
            logger.debug(f"DirtySync: Change tracked for {session_id}. Sync scheduled in {self.debounce_sec}s")

    def configure(self, *, debounce_sec: Optional[float] = None, dedupe_ttl_sec: Optional[float] = None) -> None:
        with self._lock:
            if debounce_sec is not None:
                self.debounce_sec = max(0.1, float(debounce_sec))
            if dedupe_ttl_sec is not None:
                self.dedupe_ttl_sec = max(1.0, float(dedupe_ttl_sec))

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "debounce_sec": float(self.debounce_sec),
                "dedupe_ttl_sec": float(self.dedupe_ttl_sec),
                "pending_sessions": len(self._pending_data),
                "inflight_fingerprints": len(self._inflight_fingerprints),
                "recent_fingerprints": len(self._recent_fingerprints),
                "dropped_malformed": int(self._dropped_malformed),
            }

    def _normalize_delta(self, data_delta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(data_delta, dict):
            return None
        out: Dict[str, Any] = {}
        for k, v in data_delta.items():
            if k in ("changed_files", "files", "paths"):
                if isinstance(v, list):
                    cleaned: List[Any] = []
                    for item in v:
                        if isinstance(item, str):
                            s = item.strip()
                            if s:
                                cleaned.append(s)
                        elif isinstance(item, dict):
                            cleaned.append(item)
                    out[k] = cleaned
                continue
            if isinstance(v, str):
                out[k] = v.strip()
            else:
                out[k] = v
        return out

    def _do_sync(self, session_id: str):
        data = None
        fp_to_process: List[str] = []
        with self._lock:
            data = self._pending_data.pop(session_id, None)
            self._timers.pop(session_id, None)
            self._last_trigger[session_id] = time.time()
            self._gc_recent_fingerprints_unlocked()
            if data:
                fps = self._fingerprints_from_delta(data)
                for fp in fps:
                    if fp in self._inflight_fingerprints:
                        continue
                    if fp in self._recent_fingerprints:
                        continue
                    self._inflight_fingerprints.add(fp)
                    fp_to_process.append(fp)
            
        if data and fp_to_process:
            try:
                self.sync_callback(session_id, data)
                logger.info(f"DirtySync: Successfully synchronized session {session_id}")
                with self._lock:
                    now = time.time()
                    for fp in fp_to_process:
                        self._recent_fingerprints[fp] = now
            except Exception as e:
                logger.error(f"DirtySync: Failed to sync session {session_id}: {e}")
            finally:
                with self._lock:
                    for fp in fp_to_process:
                        self._inflight_fingerprints.discard(fp)
        elif data:
            logger.debug("DirtySync: skipped duplicate delta for session %s", session_id)

    def should_sync(self, session_id: str) -> bool:
        """
        Heuristic to force sync if data volume is too high.
        """
        with self._lock:
            # If we have more than 10 keys pending, force sync
            return len(self._pending_data.get(session_id, {})) > 10

    def mark_synced(self, session_id: str):
        with self._lock:
            self._pending_data.pop(session_id, None)

    def _gc_recent_fingerprints_unlocked(self) -> None:
        now = time.time()
        expired = [k for k, ts in self._recent_fingerprints.items() if (now - ts) > float(self.dedupe_ttl_sec)]
        for k in expired:
            self._recent_fingerprints.pop(k, None)

    def _stable_hash(self, payload: Any) -> str:
        try:
            blob = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        except Exception:
            blob = str(payload)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _extract_changed_file_entries(self, data_delta: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        keys = ("changed_files", "files", "paths")
        for k in keys:
            raw = data_delta.get(k)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str):
                        entries.append({"file_path": item})
                    elif isinstance(item, dict):
                        entries.append(item)
        # Single file form
        if isinstance(data_delta.get("file_path"), str):
            entries.append(data_delta)
        elif isinstance(data_delta.get("path"), str):
            entries.append({"file_path": data_delta.get("path"), **data_delta})
        return entries

    def _resolve_content_hash(self, entry: Dict[str, Any], data_delta: Dict[str, Any]) -> str:
        for key in ("content_hash", "hash", "fingerprint"):
            val = entry.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        path = str(entry.get("file_path") or entry.get("path") or "").strip()
        for key in ("content_hash_by_path", "hash_by_path"):
            mapping = data_delta.get(key)
            if isinstance(mapping, dict):
                mapped = mapping.get(path)
                if isinstance(mapped, str) and mapped.strip():
                    return mapped.strip()
        payload = {
            "plan_summary": data_delta.get("plan_summary"),
            "actions_summary": data_delta.get("actions_summary"),
            "final_output": data_delta.get("final_output"),
            "state": data_delta.get("state"),
        }
        return self._stable_hash(payload)

    def _fingerprints_from_delta(self, data_delta: Dict[str, Any]) -> List[str]:
        file_entries = self._extract_changed_file_entries(data_delta)
        out: List[str] = []
        if file_entries:
            for entry in file_entries:
                path = str(entry.get("file_path") or entry.get("path") or "").strip()
                if not path:
                    continue
                content_hash = self._resolve_content_hash(entry, data_delta)
                out.append(f"{path}::{content_hash}")
        if out:
            return sorted(set(out))
        # Fallback for non file-based deltas.
        return [f"session-payload::{self._stable_hash(data_delta)}"]


def _extract_session_jsonl_paths(data_delta: Dict[str, Any], *, repo_root: str | Path = ".") -> List[str]:
    root = Path(repo_root).resolve()
    out: List[str] = []

    def _add_path(raw: Any) -> None:
        if not isinstance(raw, str):
            return
        s = raw.strip()
        if not s:
            return
        p = Path(s)
        if not p.is_absolute():
            p = (root / p).resolve()
        if p.suffix.lower() != ".jsonl":
            return
        out.append(str(p))

    for key in ("session_file", "session_file_path", "transcript_path", "path", "file_path"):
        _add_path(data_delta.get(key))

    for key in ("changed_files", "files", "paths"):
        raw = data_delta.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                _add_path(item)
            elif isinstance(item, dict):
                _add_path(item.get("session_file"))
                _add_path(item.get("session_file_path"))
                _add_path(item.get("transcript_path"))
                _add_path(item.get("file_path"))
                _add_path(item.get("path"))
    # Stable de-dupe
    return list(dict.fromkeys(out))


def build_memory_sync_callback(
    *,
    memory_fabric: Any,
    repo_root: str | Path = ".",
    tier: Optional[Any] = None,
    importance: float = 0.35,
) -> Callable[[str, Dict[str, Any]], None]:
    """
    Bridge DirtySync -> MemoryFabric session transcript incremental indexing.
    """
    if tier is None:
        try:
            from quentin.memory.models import MemoryTier

            tier = MemoryTier.STS
        except Exception:
            tier = None

    def _callback(session_id: str, data_delta: Dict[str, Any]) -> None:
        paths = _extract_session_jsonl_paths(data_delta, repo_root=repo_root)
        if not paths:
            return
        for p in paths:
            try:
                if tier is None:
                    memory_fabric.sync_session_file_delta(p, importance=importance)
                else:
                    memory_fabric.sync_session_file_delta(p, tier=tier, importance=importance)
            except Exception as e:
                logger.warning(
                    "DirtySync: session transcript sync failed for %s (session=%s): %s",
                    p,
                    session_id,
                    e,
                )

    return _callback

# Global instance
dirty_sync = DirtySyncManager(sync_callback=lambda sid, data: None) # Hooked in CognitiveLoop
