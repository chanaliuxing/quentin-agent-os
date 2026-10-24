from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from quentin.infra.logging import Tracer
from quentin.runtime.model_router import ModelRouter
from quentin.cognitive.schemas import ExecutionTrace, CriticReview


@dataclass
class Critic:
    """
    Critic v1（占位版）：
    - 当前实现：不用 LLM，基于 Trace 成功/失败简单生成几条 lesson
    - 后续可以在 review_with_llm 中接入 ModelRouter，生成更复杂的反思
    """
    tracer: Tracer
    model_router: ModelRouter

    async def review(self, trace: ExecutionTrace) -> CriticReview:
        """
        核心接口：给一次 ExecutionTrace 做整体评价。
        """
        if trace.success:
            summary = "Task completed successfully."
            lessons = [
                "This approach worked. Consider extracting it as a reusable skill if it repeats.",
            ]
        else:
            summary = "Task failed or encountered errors."
            lessons = [
                "Investigate the failing step and log more context for debugging.",
                "Consider adding fallback strategies or retries for the critical step.",
            ]

        # 这里可以以后扩展：
        # review_llm = await self.review_with_llm(trace)
        # 合并两者结果

        self.tracer.span(
            "L1",
            "critic_review",
            module="critic",
            input={"trace_id": trace.trace_id},
            output={"success": trace.success},
        )

        return CriticReview(summary=summary, lessons=lessons)

    async def review_with_llm(self, trace: ExecutionTrace) -> CriticReview:
        """
        预留接口：真正用 LLM 做复杂反思的地方。
        当前先返回空结果，避免强依赖。
        """
        # 将来在这里调用 self.model_router 生成更细致的分析。
        return CriticReview(summary="(LLM critic not enabled yet.)", lessons=[])
