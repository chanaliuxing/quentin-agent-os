from __future__ import annotations

import threading
import time
from pathlib import Path

from quentin.runtime.session_write_lock import acquire_session_write_lock


def test_session_write_lock_is_not_reentrant_across_threads(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("{}", encoding="utf-8")

    entered = threading.Event()
    in_cs = {"val": False}
    violated = {"val": False}

    def _t1() -> None:
        lock = acquire_session_write_lock(session_file=target, timeout_ms=2000)
        try:
            in_cs["val"] = True
            entered.set()
            time.sleep(0.35)
            in_cs["val"] = False
        finally:
            lock["release"]()

    def _t2() -> None:
        assert entered.wait(timeout=1.0)
        lock = acquire_session_write_lock(session_file=target, timeout_ms=2000)
        try:
            # If another thread bypasses the lock, it could observe in_cs==True here.
            if in_cs["val"]:
                violated["val"] = True
        finally:
            lock["release"]()

    th1 = threading.Thread(target=_t1)
    th2 = threading.Thread(target=_t2)
    th1.start()
    th2.start()
    th1.join(timeout=3.0)
    th2.join(timeout=3.0)
    assert violated["val"] is False


def test_session_write_lock_exclusive_under_contention(tmp_path: Path) -> None:
    target = tmp_path / "state2.json"
    target.write_text("{}", encoding="utf-8")

    n = 16
    barrier = threading.Barrier(n)
    counter_lock = threading.Lock()
    state = {"in_cs": 0, "max_in_cs": 0, "timeouts": 0}

    def _worker() -> None:
        try:
            barrier.wait(timeout=2.0)
        except Exception:
            return
        try:
            held = acquire_session_write_lock(session_file=target, timeout_ms=10_000)
        except TimeoutError:
            with counter_lock:
                state["timeouts"] += 1
            return
        try:
            with counter_lock:
                state["in_cs"] += 1
                state["max_in_cs"] = max(state["max_in_cs"], state["in_cs"])
            time.sleep(0.01)
            with counter_lock:
                state["in_cs"] -= 1
        finally:
            held["release"]()

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=3.0)

    assert int(state["timeouts"]) == 0
    assert int(state["max_in_cs"]) == 1
