from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
from quentin.utils.time import now_utc


@dataclass
class ScheduledTask:
    name: str
    fn: Callable[[], None]
    interval_seconds: int
    max_runs_per_window: int
    window_seconds: int = 24 * 3600
    enabled: bool = True

    # runtime 状态
    last_run_at: Optional[datetime] = None
    window_start_at: datetime = field(default_factory=lambda: now_utc())
    runs_in_window: int = 0

    def _reset_window_if_needed(self, now: datetime) -> None:
        if now - self.window_start_at >= timedelta(seconds=self.window_seconds):
            self.window_start_at = now
            self.runs_in_window = 0

    def should_run(self, now: datetime) -> bool:
        if not self.enabled:
            return False

        self._reset_window_if_needed(now)

        if self.runs_in_window >= self.max_runs_per_window:
            return False

        if self.last_run_at is None:
            # 第一次可以直接跑
            return True

        if (now - self.last_run_at).total_seconds() >= self.interval_seconds:
            return True

        return False

    def mark_ran(self, when: datetime) -> None:
        self.last_run_at = when
        self.runs_in_window += 1
