# quentin/l3/research/cog_bridge.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from quentin.cognitive.loop import CognitiveTask, CognitiveResult
from quentin.critic.task_council import CriticFeedback
from quentin.l3.research.experiments import ResearchManager, Experiment

logger = logging.getLogger(__name__)


class CognitiveResearchBridge:
    """
    把 CognitiveLoop 的 TaskResult 作为在线实验数据写入 ResearchManager。

    策略：
      - capability  : "cogloop:<domain>"
      - requirement : "task_success"
      - purpose     : "cogloop_online"

      - variant_id  : "default"（后续可以扩展为不同 agent_version / 策略）
      - metrics:
          success           : bool
          critic_confidence : float
          has_error         : bool
          duration_seconds  : float
    """

    def __init__(self, rm: Optional[ResearchManager] = None) -> None:
        self.rm = rm or ResearchManager()

    def record_task_outcome(
        self,
        task: CognitiveTask,
        result: CognitiveResult,
        feedback: Optional[CriticFeedback],
    ) -> None:
        capability = f"cogloop:{task.domain}"
        requirement_id = "task_success"

        exp = self._get_or_create_experiment(
            capability=capability,
            requirement_id=requirement_id,
        )

        metrics: Dict[str, Any] = {
            "success": bool(getattr(result, "done", False)),
            "critic_confidence": float(getattr(feedback, "score", 0.0)) if feedback else None,
            "has_error": bool("error" in (getattr(result, "final_output", "") or "").lower()),
            "duration_seconds": None,
        }

        context = {
            "task_id": task.task_id,
            "goal": (task.goal_description or task.input_text or "")[:200],
            "domain": task.domain,
        }

        self.rm.record_run(
            experiment_id=exp.experiment_id,
            variant_id="default",
            metrics=metrics,
            context=context,
        )

    # ---------- 内部 ----------

    def _get_or_create_experiment(
        self,
        *,
        capability: str,
        requirement_id: str,
    ) -> Experiment:
        exps = self.rm.list_experiments()
        for e in exps:
            if (
                e.capability == capability
                and e.requirement_id == requirement_id
                and e.purpose == "cogloop_online"
            ):
                return e

        return self.rm.create_experiment(
            name=f"CognitiveLoop-{capability}-{requirement_id}",
            purpose="cogloop_online",
            capability=capability,
            requirement_id=requirement_id,
            tags=["cognitive_loop", "online"],
        )

    # NOTE: The canonical `CognitiveResult` does not currently expose started/finished timestamps.
    # Keep duration_seconds as None for now. If/when the loop records timing, wire it here.
