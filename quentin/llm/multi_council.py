# quentin/llm/multi_council.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

from quentin.llm.types import LLMConfig
from quentin.traces.core import TraceRecorder, TraceEventType, new_trace_event
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)


@dataclass
class CouncilMemberOpinion:
    model: str
    role: str
    answer: str
    notes: str = ""  # 可以记录“偏向速度”、“偏向安全”等描述

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilDecision:
    final_answer: str
    reasoning: str
    opinions: List[CouncilMemberOpinion]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "reasoning": self.reasoning,
            "opinions": [o.to_dict() for o in self.opinions],
        }


class MultiAICouncil:
    """
    多模型“开会”模式 v1：

    流程：
      1. 每个 LLM 成员单独给出自己的 proposal。
      2. 选一个模型做“主持人/整合者”，看到所有 proposal 后给出综合结论。
    """

    def __init__(
        self,
        members: List[LLMConfig],
        trace_recorder: Optional[TraceRecorder] = None,
    ) -> None:
        if not members:
            raise ValueError("MultiAICouncil requires at least one LLM member.")
        self.members = members
        self.trace_recorder = trace_recorder

    # ---------- 主 API ----------

    def deliberate(
        self,
        *,
        question: str,
        context: Optional[str] = None,
        mode: str = "general",
        domain: str = "core",
        environment: str = "sandbox",
        risk_level: str = "medium",
        safety_kernel: Any = None,
    ) -> CouncilDecision:
        """
        - question : 要解决的核心问题（如“如何修这个代码？”）
        - context  : 背景（蓝皮书 requirement、现有代码路径等）
        - mode     : "plan" / "reflection" / "coding" 等，用于提示角色
        """
        if self.trace_recorder is not None:
            try:
                self.trace_recorder.record_event(
                    new_trace_event(
                        trace_id="multi_ai_council",
                        event_type=TraceEventType.DECISION,
                        payload={"action": "deliberate_start", "mode": mode},
                    )
                )
            except Exception:
                pass

        # 1) 每个成员给出意见
        opinions: List[CouncilMemberOpinion] = []
        for m in self.members:
            prompt = self._build_member_prompt(
                role=m.role,
                mode=mode,
                question=question,
                context=context,
            )
            answer = call_llm(
                m.model,
                user_prompt=prompt,
                system_prompt="",
                provider=m.provider,
                model_name=m.model,
                safety_kernel=safety_kernel,
                actor=f"multi_ai_council_member:{m.role}",
                domain=domain,
                environment=environment,
                risk_level=risk_level,
                action_metadata={
                    "council_mode": mode,
                    "council_role": m.role,
                    "council_operation": "member",
                    # Prevent recursion: council deliberation should not trigger another policy borderline council.
                    "bypass_ai_council": True,
                },
            )
            opinions.append(
                CouncilMemberOpinion(
                    model=m.model,
                    role=m.role,
                    answer=answer,
                    notes="",
                )
            )

        # 2) 选一个“主持人”，整合大家意见
        aggregator = self.members[0]
        agg_prompt = self._build_aggregator_prompt(
            mode=mode,
            question=question,
            context=context,
            opinions=opinions,
        )
        final_answer = call_llm(
            aggregator.model,
            user_prompt=agg_prompt,
            system_prompt="",
            provider=aggregator.provider,
            model_name=aggregator.model,
            safety_kernel=safety_kernel,
            actor="multi_ai_council_chair",
            domain=domain,
            environment=environment,
            risk_level=risk_level,
            action_metadata={
                "council_mode": mode,
                "council_role": aggregator.role,
                "council_operation": "chair",
                # Prevent recursion: council deliberation should not trigger another policy borderline council.
                "bypass_ai_council": True,
            },
        )

        reasoning = (
            "Aggregated by model "
            f"{aggregator.model} in role '{aggregator.role}' "
            "based on the above member opinions."
        )

        decision = CouncilDecision(
            final_answer=final_answer,
            reasoning=reasoning,
            opinions=opinions,
        )
        if self.trace_recorder is not None:
            try:
                self.trace_recorder.record_event(
                    new_trace_event(
                        trace_id="multi_ai_council",
                        event_type=TraceEventType.DECISION,
                        payload={"action": "deliberate_done", "mode": mode, "members": len(self.members)},
                    )
                )
            except Exception:
                pass

        return decision

    # ---------- Prompt 构造 ----------

    def _build_member_prompt(
        self,
        *,
        role: str,
        mode: str,
        question: str,
        context: Optional[str],
    ) -> str:
        ctx = context or ""
        return (
            f"You are an AI committee member with role '{role}'.\n"
            f"Task mode: {mode}.\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Context (if any):\n"
            f"{ctx}\n\n"
            "Please provide your best proposal. "
            "Focus on clarity, concrete steps, and avoid vague language. "
            "Output plain text, no markdown unless needed for code blocks."
        )

    def _build_aggregator_prompt(
        self,
        *,
        mode: str,
        question: str,
        context: Optional[str],
        opinions: List[CouncilMemberOpinion],
    ) -> str:
        ctx = context or ""
        opinions_text = ""
        for idx, op in enumerate(opinions, start=1):
            opinions_text += (
                f"--- Opinion {idx} ---\n"
                f"model: {op.model}\n"
                f"role : {op.role}\n"
                f"text : {op.answer}\n\n"
            )

        return (
            "You are the chair of an AI committee.\n"
            f"Task mode: {mode}.\n\n"
            "You are given a question, some context, and multiple member opinions. "
            "Your job is to:\n"
            "1) Compare the opinions.\n"
            "2) Resolve contradictions.\n"
            "3) Produce a single, coherent final answer.\n"
            "4) If appropriate, mention which ideas you adopted from which opinions.\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Context:\n"
            f"{ctx}\n\n"
            "Member opinions:\n"
            f"{opinions_text}\n"
            "Now write your final consolidated answer. "
            "Be specific and practical. "
            "If the task is about CODE, prefer to output a single code block or patch."
        )
