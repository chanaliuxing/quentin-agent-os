from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class _HeldLock:
    count: int
    lock_path: Path


_HELD_LOCKS: dict[tuple[Path, int], _HeldLock] = {}
_HELD_LOCKS_LOCK = threading.Lock()


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_lock_payload(lock_path: Path) -> Optional[dict]:
    try:
        raw = lock_path.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return None


def _lock_file_age_ms(lock_path: Path) -> float:
    try:
        st = lock_path.stat()
        return max(0.0, (time.time() - float(st.st_mtime)) * 1000.0)
    except Exception:
        return 0.0


def acquire_session_write_lock(
    *,
    session_file: str | Path,
    timeout_ms: int = 10_000,
    stale_ms: int = 30 * 60 * 1000,
) -> dict:
    session_path = Path(session_file).resolve()
    tid = threading.get_ident()
    key = (session_path, tid)
    lock_path = session_path.with_suffix(session_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with _HELD_LOCKS_LOCK:
        held = _HELD_LOCKS.get(key)
        if held is not None:
            held.count += 1
            return {"release": lambda: _release_lock(key)}

    started = time.time()
    attempt = 0
    while (time.time() - started) * 1000 < timeout_ms:
        attempt += 1
        try:
            with open(lock_path, "x", encoding="utf-8") as f:
                payload = {"pid": os.getpid(), "created_at": time.time()}
                f.write(json.dumps(payload))
            with _HELD_LOCKS_LOCK:
                _HELD_LOCKS[key] = _HeldLock(count=1, lock_path=lock_path)
            return {"release": lambda: _release_lock(key)}
        except FileExistsError:
            payload = _read_lock_payload(lock_path)
            created_at = (payload or {}).get("created_at")
            pid = (payload or {}).get("pid")
            age_ms = _lock_file_age_ms(lock_path)

            stale_by_payload = isinstance(created_at, (int, float)) and ((time.time() - float(created_at)) * 1000.0 > stale_ms)
            stale_by_age = age_ms > float(stale_ms)

            # If we can't parse payload (lock being created) or pid is missing, be conservative:
            # do not delete unless the file is clearly stale by age.
            alive = _is_alive(pid) if isinstance(pid, int) else True
            stale = bool(stale_by_payload or stale_by_age or ((not alive) and age_ms > 1000.0))

            if stale:
                try:
                    lock_path.unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            time.sleep(min(1.0, 0.05 * attempt))

    owner = _read_lock_payload(lock_path) or {}
    raise TimeoutError(
        f"session file locked (timeout {timeout_ms}ms): pid={owner.get('pid')} path={lock_path}"
    )


def _release_lock(key: tuple[Path, int]) -> None:
    with _HELD_LOCKS_LOCK:
        held = _HELD_LOCKS.get(key)
        if held is None:
            return
        held.count -= 1
        if held.count > 0:
            return
        _HELD_LOCKS.pop(key, None)
    try:
        held.lock_path.unlink(missing_ok=True)
    except Exception:
        pass
