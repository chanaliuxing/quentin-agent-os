from __future__ import annotations

from dataclasses import dataclass
from typing import List
import uuid

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.self_improvement.manager import SelfImprovementManager
from quentin.kernel.schemas import (
    ExecutionSummary,
    TaskStatus,
    SkillStatus,
)
from quentin.skills.skill_library import SkillLibrary


@dataclass
class SkillMiner:
    """
    从历史成功任务中抽取“可复用技能”（简单版）：
    - 筛选：成功 && 步骤数 >= 2
    - 生成技能：pattern_goal = task_goal，steps = 该任务的 step trace（压缩成工具+参数）
    - 避免重复：用 mined_task_ids 做去重
    """
    kv: KVStore
    tracer: Tracer
    self_improvement: SelfImprovementManager
    skill_library: SkillLibrary
    mined_prefix: str = "skill_miner:mined_task_ids"

    async def _get_mined_task_ids(self) -> set[str]:
        ids = await self.kv.get(self.mined_prefix) or []
        return set(ids)

    async def _add_mined_task_id(self, task_id: str) -> None:
        ids = await self.kv.get(self.mined_prefix) or []
        ids.append(task_id)
        await self.kv.save(self.mined_prefix, ids)

    def _summary_to_skill_steps(self, summary: ExecutionSummary) -> List[dict]:
        steps = []
        for s in summary.steps:
            steps.append(
                {
                    "description": f"[{s.tool}] auto-mined step for task {summary.task_id}",
                    "tool": s.tool,
                    "params": s.input or {},
                }
            )
        return steps

    async def run_mining_once(
        self,
        max_new_skills: int = 3,
        min_steps: int = 2,
    ) -> List[str]:
        """
        执行一次简单的 Skill Mining：
        - 最多产生 max_new_skills 个新技能
        - 返回 skill_id 列表
        """
        summaries = await self.self_improvement.list_summaries()
        if not summaries:
            self.tracer.span(
                "L2",
                "skill_miner_no_data",
                module="skill_miner",
                output={"num_summaries": 0},
            )
            return []

        mined_ids = await self._get_mined_task_ids()
        created_skill_ids: List[str] = []

        # From old to new to ensure stable mining
        summaries.sort(key=lambda s: s.started_at)

        for summary in summaries:
            if len(created_skill_ids) >= max_new_skills:
                break

            if summary.task_id in mined_ids:
                continue
            if summary.status != TaskStatus.success:
                continue
            if len(summary.steps) < min_steps:
                continue

            steps = self._summary_to_skill_steps(summary)
            name = f"auto_skill::{summary.domain}::{uuid.uuid4().hex[:8]}"
            description = f"Auto-mined skill from task {summary.task_id}"
            skill = await self.skill_library.create_skill(
                name=name,
                description=description,
                domain=summary.domain,
                pattern_goal=summary.task_goal,
                steps=steps,
                tags=["auto_mined"],
                created_from_task_ids=[summary.task_id],
                status=SkillStatus.active,  # Directly activate as MVP
            )

            created_skill_ids.append(skill.skill_id)
            await self._add_mined_task_id(summary.task_id)

        self.tracer.span(
            "L2",
            "skill_miner_done",
            module="skill_miner",
            output={
                "num_created": len(created_skill_ids),
                "created_skill_ids": created_skill_ids,
            },
        )
        return created_skill_ids
