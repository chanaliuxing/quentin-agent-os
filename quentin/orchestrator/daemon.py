from __future__ import annotations
from typing import List
import time
import signal
import threading

from quentin.orchestrator.models import ScheduledTask
from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType # Import new_trace_event and TraceEventType
from quentin.utils.time import now_iso, now_utc

# 各个 loop 的导入
# Note: These imports are placeholders and will need to be adjusted
# to the actual location of the run functions for each loop.
# from quentin.runtime.sleep_loop import run_sleep_cycle
# from quentin.skills.evolution import run_skill_evolution_cycle
# from quentin.self_programming.skill_impl_runner import run_skill_impl_cycle
# from quentin.cli.blueprint_runner import run_blueprint_self_iteration

trace_recorder = JsonlTraceRecorder(repo_root=".")


class OrchestratorDaemon:
    def __init__(self, poll_interval_seconds: int = 30):
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self.tasks: List[ScheduledTask] = []

    # ---- lifecycle ----

    def register_task(self, task: ScheduledTask) -> None:
        self.tasks.append(task)

    def stop(self) -> None:
        self._stop_event.set()

    def _handle_signal(self, signum, frame) -> None:
        trace_recorder.record_event(
            new_trace_event(
                trace_id="orchestrator",
                event_type=TraceEventType.ERROR, # Or a specific signal event type
                payload={"signal": signum},
            )
        )
        self.stop()

    def run_forever(self) -> None:
        # 注册信号处理，方便优雅退出
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        trace_recorder.record_event(
            new_trace_event(
                trace_id="orchestrator",
                event_type=TraceEventType.EXECUTION, # Or a specific daemon start event type
                payload={"poll_interval": self.poll_interval_seconds},
            )
        )

        while not self._stop_event.is_set():
            now = now_utc()

            for task in self.tasks:
                if not task.enabled:
                    continue
                if not task.should_run(now):
                    continue

                trace_recorder.record_event(
                    new_trace_event(
                        trace_id="orchestrator",
                        event_type=TraceEventType.EXECUTION, # Or a specific task start event type
                        payload={
                            "task_name": task.name,
                            "ts": now.isoformat(),
                        },
                    )
                )

                try:
                    task.fn()
                    task.mark_ran(now)

                    trace_recorder.record_event(
                        new_trace_event(
                            trace_id="orchestrator",
                            event_type=TraceEventType.EXECUTION, # Or a specific task done event type
                            payload={
                                "task_name": task.name,
                                "ts": now_iso(),
                                "status": "success",
                                "runs_in_window": task.runs_in_window,
                            },
                        )
                    )
                except Exception as e:
                    # v1 简单记录错误，不立刻停整个 daemon
                    trace_recorder.record_event(
                        new_trace_event(
                            trace_id="orchestrator",
                            event_type=TraceEventType.ERROR,
                            payload={
                                "task_name": task.name,
                                "ts": now_iso(),
                                "error": repr(e),
                            },
                        )
                    )

            # 休息一会再检查
            time.sleep(self.poll_interval_seconds)

        trace_recorder.record_event(
            new_trace_event(
                trace_id="orchestrator",
                event_type=TraceEventType.EXECUTION, # Or a specific daemon stopped event type
                payload={"ts": now_iso()},
            )
        )
