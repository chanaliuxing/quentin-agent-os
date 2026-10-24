from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from quentin.runtime.task_source_registry import TaskSource, TaskSourceContext, TaskSourceRunReport as RegistryTaskSourceRunReport, TaskSourceSpec
from quentin.runtime.task_queue import TaskQueueItem
from quentin.skills.candidate_pipeline import SkillCandidateStore

def _bool_env(name: str, default: str = "1") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

class SkillMiningTaskSource(TaskSource):
    """
    Picks up SkillCandidates from the Miner and enqueues them for Self-Programming.
    """
    def __init__(self) -> None:
        self._spec = TaskSourceSpec(
            id="skill_mining",
            name="SkillMiningTasks",
            kind="maintenance",
            priority=70,
            default_enabled=True,
            max_per_run=5,
            cooldown_sec=float(os.getenv("QUENTIN_TASK_SOURCE_SKILL_MINING_COOLDOWN_SEC", "0") or "0"),
        )

    @property
    def spec(self) -> TaskSourceSpec:
        return self._spec

    def enabled(self, ctx: TaskSourceContext) -> bool:
        return _bool_env("QUENTIN_TASK_SOURCE_SKILL_MINING", "1")

    def max_per_run(self, ctx: TaskSourceContext) -> int:
        raw = (os.getenv("QUENTIN_TASK_SOURCE_SKILL_MINING_MAX", "") or "").strip()
        if raw:
            try:
                return int(raw)
            except Exception:
                pass
        return int(self._spec.max_per_run or 5)

    async def run(self, ctx: TaskSourceContext) -> RegistryTaskSourceRunReport:
        store = SkillCandidateStore()
        candidates = store.load_pending()
        
        enq = 0
        skipped = 0
        details = []
        
        max_n = self.max_per_run(ctx)
        
        for cand in candidates[:max_n]:
            # Convert candidate to a maintenance task
            item = TaskQueueItem.new(
                input_text=f"[maintenance] Implement and verify mined skill: {cand.name} ({cand.domain}).",
                domain=ctx.domain,
                environment=ctx.environment,
                session_id=ctx.session_id,
                priority=7, # Medium-high priority
                metadata={
                    "source": "skill_mining",
                    "kind": "skill_implementation",
                    "candidate_id": cand.candidate_id,
                    "skill_name": cand.name,
                    "domain": cand.domain,
                    "target_file": f"quentin/skills/generated/skill_{cand.name.lower()}.py"
                },
            )
            ctx.queue.append(item)
            enq += 1
            details.append({"task_id": item.task_id, "candidate_id": cand.candidate_id})
            
        return RegistryTaskSourceRunReport(
            source_id=self.spec.id,
            status="ok",
            reason="ok" if enq > 0 else "no_candidates",
            enqueued=enq,
            skipped=skipped,
            details=details
        )
