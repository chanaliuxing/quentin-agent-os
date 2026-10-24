# meta_agent/evolution/schedule_config.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

@dataclass
class SelfEvolutionScheduleConfig:
    """
    Minimal self-evolution schedule settings.

    This is intentionally small: it exists to keep runtime wiring stable and to
    support observability tooling. Higher-level policy can evolve separately.
    """

    max_runs_per_day_by_loop: Dict[str, int] = field(default_factory=lambda: {
        "blueprint_improvement": 12,
        "sleep": 24,
        "immune": 48,
        "self_programming": 24,
    })

    def max_runs_per_day(self, loop_name: str) -> int:
        return int(self.max_runs_per_day_by_loop.get(loop_name, 0))
