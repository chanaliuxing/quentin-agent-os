# quentin/self_improvement/auto_bridge.py
from __future__ import annotations

import logging
import uuid
from typing import Optional, List

from quentin.cognitive.loop import CognitiveTask, CognitiveResult
from quentin.critic.task_council import CriticFeedback
from quentin.self_improvement.manager import SelfImprovementManager
from quentin.self_improvement.schemas import ImprovementTask

logger = logging.getLogger(__name__)


class AutoImprovementBridge:
    """
    把 CognitiveLoop 中的“失败任务 / 低置信任务”，自动转成 ImprovementTask。

    设计原则：
      - 不对“每一个小错误”都建任务，否则会淹没自己；
      - 针对“明显失败 / 置信度很低 / critic 分数很低”的任务，生成一条改进任务；
      - capability 命名为：cogloop:<domain>
      - requirement_id 固定先用：task_quality
    """

    def __init__(
        self,
        *,
        si_manager: Optional[SelfImprovementManager] = None,
        min_confidence: float = 0.6,
    ) -> None:
        self.si_manager = si_manager or SelfImprovementManager()
        self.min_confidence = min_confidence

    # ---------- 主入口 ----------

    def maybe_create_from_cog_result(
        self,
        task: CognitiveTask,
        result: CognitiveResult,
        feedback: CriticFeedback,
    ) -> Optional[ImprovementTask]:
        """
        根据 CognitiveResult + CriticFeedback 判断是否需要创建 ImprovementTask。
        """
        need = self._should_create(task, result, feedback)
        if not need:
            return None

        # 防止重复：同一个 original_task_id 只建一次
        existing = self._find_existing_for_task(task.task_id)
        if existing:
            logger.info(
                "AutoImprovementBridge: task_id=%s already has ImprovementTask=%s",
                task.task_id,
                existing.task_id,
            )
            return existing

        capability = f"cogloop:{task.domain}"
        requirement_id = "task_quality"

        goal_text = (task.goal_description or task.goal_title or task.input_text or "").strip()
        final_output = getattr(result, "final_output", "") or ""
        desc = (
            f"Auto-created from CognitiveLoop failure.\n"
            f"- Original task_id: {task.task_id}\n"
            f"- Goal: {goal_text}\n\n"
            f"- Done: {getattr(result, 'done', False)} (confidence={getattr(result, 'done_confidence', 0.0):.3f})\n\n"
            f"- Final output (truncated):\n{final_output[:1200]}\n\n"
            f"- Critic score: {getattr(feedback, 'score', 0.0)}\n"
            f"- Critic reflection (truncated):\n{(getattr(feedback, 'reflection', '') or '')[:1200]}\n\n"
            f"- Next action hint (truncated):\n{(getattr(feedback, 'next_action_hint', '') or '')[:600]}"
        )

        it = ImprovementTask(
            task_id=str(uuid.uuid4()),
            capability=capability,
            requirement_id=requirement_id,
            description=desc,
            # source="cognitive_loop.auto", # Not in schema, add to meta
            overall_status="todo",
            metadata={
                "source": "cognitive_loop.auto",
                "original_task_id": task.task_id,
                "domain": task.domain,
                "goal": goal_text,
            },
        )
        self.si_manager.upsert_task(it)
        logger.info(
            "AutoImprovementBridge: created ImprovementTask=%s for original_task_id=%s",
            it.task_id,
            task.task_id,
        )
        return it

    # ---------- 内部逻辑 ----------

    def _should_create(
        self,
        task: CognitiveTask,
        result: CognitiveResult,
        feedback: CriticFeedback,
    ) -> bool:
        _ = task
        done = bool(getattr(result, "done", False))
        done_confidence = float(getattr(result, "done_confidence", 0.0) or 0.0)
        if not done:
            return True
        if done_confidence < self.min_confidence:
            return True
        # If we have a critic council score, treat low score as a trigger.
        try:
            score = float(getattr(feedback, "score", 1.0))
        except Exception:
            score = 1.0
        if score < 0.5:
            return True
        return False

    def _find_existing_for_task(self, original_task_id: str) -> Optional[ImprovementTask]:
        tasks: List[ImprovementTask] = self.si_manager.list_tasks()
        for t in tasks:
            meta = getattr(t, "metadata", {}) or {}
            if meta.get("original_task_id") == original_task_id:
                return t
        return None
