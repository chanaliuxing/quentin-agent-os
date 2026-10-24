from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class EchoPlanner:
    """
    Minimal fallback planner used by bootstrap wiring and demos.

    New code should prefer `quentin.planning.hierarchical_planner.HierarchicalPlanner`.
    """

    def plan(self, goal: str, context: Dict[str, Any]) -> str:
        _ = context
        return f"Echo Plan: {goal}"
