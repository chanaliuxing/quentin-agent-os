from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import json
import logging

from quentin.llm.multi_council import MultiAICouncil, CouncilDecision
from quentin.llm.types import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class CriticReport:
    success: bool
    score: float
    reflection: str
    next_action_hint: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CriticFeedback = CriticReport


class TaskCritic:
    """
    Task-level critic council (legacy).
    """

    def __init__(self, council: Optional[MultiAICouncil] = None) -> None:
        if council is None:
            import os
            main_model = os.getenv("LLM_MODEL")
            if not main_model:
                 raise ValueError("Environment variable LLM_MODEL is not set.")
            critic_model = os.getenv("LLM_MODEL_CRITIC") or main_model
            members = [
                LLMConfig(provider="ollama", model=main_model, role="task_judge"),
                LLMConfig(provider="ollama", model=critic_model, role="reflection_helper"),
            ]
            council = MultiAICouncil(members=members)
        self.council = council

    def review(
        self,
        *,
        task_description: str,
        plan_steps: List[str],
        step_outputs: List[str],
    ) -> CriticReport:
        ctx_lines: List[str] = ["TASK DESCRIPTION:", task_description, "", "PLAN STEPS:"]
        for i, s in enumerate(plan_steps):
            ctx_lines.append(f"{i+1}. {s}")

        ctx_lines.append("")
        ctx_lines.append("STEP OUTPUTS:")
        for i, s in enumerate(step_outputs):
            ctx_lines.append(f"{i+1}. {s}")

        context = "\n".join(ctx_lines)

        question = (
            "You are a CRITIC COUNCIL evaluating a task execution.\n\n"
            "Return ONLY ONE JSON object:\n"
            "{\n"
            "  \"success\": true/false,\n"
            "  \"score\": 0.0-1.0,\n"
            "  \"reflection\": \"...\",\n"
            "  \"next_action_hint\": \"...\"\n"
            "}"
        )

        decision: CouncilDecision = self.council.deliberate(question=question, context=context, mode="task_critic")
        ans = decision.final_answer or "{}"

        try:
            s = ans.strip()
            first = s.find("{")
            last = s.rfind("}")
            if first != -1 and last != -1 and last > first:
                s = s[first : last + 1]
            data = json.loads(s)
        except Exception:
            logger.exception("TaskCritic.review: failed to parse council JSON")
            data = {
                "success": False,
                "score": 0.0,
                "reflection": "Failed to parse critic council answer.",
                "next_action_hint": "Retry with clearer constraints.",
            }

        success = bool(data.get("success", False))
        try:
            score = float(data.get("score", 0.0))
        except Exception:
            score = 0.0

        return CriticReport(
            success=success,
            score=score,
            reflection=str(data.get("reflection", "") or ""),
            next_action_hint=str(data.get("next_action_hint", "") or ""),
        )

