from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from quentin.runtime.brain_daemon import BrainDaemon, BrainDaemonConfig


class _LaneProbeLoop:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def run_task(self, task):  # type: ignore[no-untyped-def]
        _ = task
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.12)
        with self._lock:
            self.active -= 1
        return SimpleNamespace(
            task_id="t1",
            goal_id="g1",
            done=False,
            done_confidence=0.0,
            final_output="ok",
            self_awareness={},
        )


class _DummySleep:
    def run_once(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


class _DummyImmune:
    def process_trace(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


def test_brain_daemon_run_once_serializes_same_session_lane(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    probe = _LaneProbeLoop()
    container = SimpleNamespace(cognitive_loop=probe, sleep_loop=_DummySleep(), immune_loop=_DummyImmune())
    daemon = BrainDaemon(
        config=BrainDaemonConfig(session_id="lane-s1", run_sleep_loop=False, run_immune_loop=False),
        container=container,  # type: ignore[arg-type]
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(daemon.run_once, input_text="a")
        f2 = pool.submit(daemon.run_once, input_text="b")
        _ = f1.result(timeout=5)
        _ = f2.result(timeout=5)

    assert probe.max_active == 1
