from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import asyncio
import uuid


@dataclass
class SelfProgrammingTrigger:
    session_id: str
    trace_id: str
    goal_id: str
    task_id: str
    reason: str
    error: str
    actions_summary: str
    related_files: List[str]
    meta: Dict[str, Any]


class SelfProgrammingHook:
    """
    Governance entrypoint for self-programming triggers.

    Design goal:
    - Core loop never writes files directly for self-programming.
    - All patch application must flow through SafePatchApplier / PathGuard / SafetyKernel,
      which is enforced inside the self-programming engine implementation.
    """

    def __init__(self, *, loop: Any) -> None:
        self.loop = loop

    def trigger_self_heal(self, trig: SelfProgrammingTrigger) -> None:
        queue = getattr(self.loop, "system_event_queue", None)
        try:
            if queue is not None:
                queue.emit_brain_event(
                    session_id=str(trig.session_id or "global"),
                    event_type="selfprog.triggered",
                    category="self_programming",
                    phase="trigger",
                    source="cognitive_loop",
                    payload={
                        "trace_id": trig.trace_id,
                        "goal_id": trig.goal_id,
                        "task_id": trig.task_id,
                        "reason": trig.reason,
                        "error": trig.error[:800],
                        "related_files": trig.related_files[:12],
                        "meta": trig.meta,
                    },
                    turn_id=str(trig.goal_id or ""),
                )
        except Exception:
            pass

        engine = getattr(self.loop, "self_programming_engine", None)
        if not (getattr(self.loop, "self_programming_enabled", False) and engine is not None):
            return

        try:
            from quentin.self_programming.engine import BlueprintGap
        except Exception:
            return

        gap = BlueprintGap(
            id=f"heal-{uuid.uuid4().hex[:8]}",
            title=f"Self-healing for recurring error: {trig.error[:60]}",
            description=(
                "System encountered a recurring error during task execution.\n"
                f"Reason: {trig.reason}\n"
                f"Error: {trig.error}\n"
                f"Last Actions: {trig.actions_summary}"
            ),
            related_files=list(trig.related_files or []),
        )

        try:
            asyncio.create_task(engine.run_cycle_for_gap(gap))
        except Exception:
            pass

