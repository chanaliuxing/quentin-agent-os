from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from quentin.runtime.task_source_registry import TaskSource, TaskSourceContext, TaskSourceRunReport as RegistryTaskSourceRunReport, TaskSourceSpec
from quentin.runtime.task_enqueue_utils import enqueue_blueprint_gap_tasks

def _bool_env(name: str, default: str = "1") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

class BlueprintTaskSource(TaskSource):
    def __init__(self) -> None:
        self._spec = TaskSourceSpec(
            id="blueprint",
            name="BlueprintGapTasks",
            kind="maintenance",
            priority=100,
            default_enabled=True,
            max_per_run=25,
            cooldown_sec=float(os.getenv("QUENTIN_TASK_SOURCE_BLUEPRINT_COOLDOWN_SEC", "0") or "0"),
        )

    @property
    def spec(self) -> TaskSourceSpec:
        return self._spec

    def enabled(self, ctx: TaskSourceContext) -> bool:
        return _bool_env("QUENTIN_TASK_SOURCE_BLUEPRINT", "1")

    def max_per_run(self, ctx: TaskSourceContext) -> int:
        raw = (ctx.env.get("QUENTIN_TASK_SOURCE_BLUEPRINT_MAX") or os.getenv("QUENTIN_TASK_SOURCE_BLUEPRINT_MAX") or "").strip()
        if raw:
            try:
                return int(raw)
            except Exception:
                pass
        return int(self._spec.max_per_run or 25)

    async def run(self, ctx: TaskSourceContext) -> RegistryTaskSourceRunReport:
        max_n = max(0, int(self.max_per_run(ctx)))
        if max_n <= 0:
            return RegistryTaskSourceRunReport(source_id=self.spec.id, status="skipped", reason="budget_exhausted")
        r = enqueue_blueprint_gap_tasks(
            queue=ctx.queue,
            tracker=None,
            limit=max_n,
            domain=ctx.domain,
            environment=ctx.environment,
            session_id=ctx.session_id,
        )
        if int(r.enqueued) <= 0:
            return RegistryTaskSourceRunReport(
                source_id=self.spec.id,
                status="ok",
                reason="no_candidates",
                enqueued=int(r.enqueued),
                skipped=int(r.skipped),
                details=list(r.details),
            )
        return RegistryTaskSourceRunReport(
            source_id=self.spec.id,
            status="ok",
            reason="ok",
            enqueued=int(r.enqueued),
            skipped=int(r.skipped),
            details=list(r.details),
        )
