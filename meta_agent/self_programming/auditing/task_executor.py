from __future__ import annotations

from typing import List, Dict, Any

from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, SelfProgrammingConfig, GapLike


class RemediationTaskExecutor:
    """
    Convert remediation tasks into ProgrammingTask-like gaps and feed into SelfProgrammingEngineV2.
    This is a thin adapter; it does not auto-approve patches beyond engine's own governance.
    """

    def __init__(self, engine: SelfProgrammingEngineV2 | None = None):
        cfg = SelfProgrammingConfig(allow_auto_apply=False, enable_research=False)
        self.engine = engine or SelfProgrammingEngineV2(config=cfg)

    def run_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        gaps: List[GapLike] = []
        for t in tasks:
            gaps.append(
                GapLike(
                    id=t.get("req_id", ""),
                    title=f"Remediate {t.get('req_id', '')}: {t.get('task_type')}",
                    description=self._build_description(t),
                    category="audit_fix",
                    priority=1,
                    related_files=[t.get("module_hint", "")] if t.get("module_hint") else [],
                )
            )
        if not gaps:
            return
        self.engine.run_for_gaps(gaps)

    def _build_description(self, task: Dict[str, Any]) -> str:
        desc = [
            f"Task type: {task.get('task_type')}",
            f"Recommendation: {task.get('recommendation')}",
            f"Missing items: {task.get('missing_items')}",
            f"Status: {task.get('status')}, confidence: {task.get('confidence')}",
        ]
        return "\n".join(desc)
