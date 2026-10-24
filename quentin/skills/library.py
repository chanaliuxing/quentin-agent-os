from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

import uuid
from quentin.utils.time import now_utc

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.skills.schemas import SkillDefinition, SkillStats


@dataclass
class SkillLibrary:
    """
    SkillLibrary v1：

    - 提供 Skill 的注册、查询、列出、统计更新
    - 所有数据存 KV，方便以后切换 Redis / DB / 文件
    """

    tracer: Tracer
    kv: KVStore

    skill_prefix: str = "skill:def:"
    stats_prefix: str = "skill:stats:"
    index_key: str = "skill:index:all"
    name_index_key: str = "skill:index:name"

    # ---------- 工具方法 ----------

    async def _save_skill(self, skill: SkillDefinition) -> None:
        key = f"{self.skill_prefix}{skill.skill_id}"
        await self.kv.save(key, skill.model_dump())
        await self.kv.append_list(self.index_key, skill.skill_id)
        # name 索引：允许按 name 查最新版本
        await self.kv.hset(self.name_index_key, skill.name, skill.skill_id)

    async def _save_stats(self, stats: SkillStats) -> None:
        key = f"{self.stats_prefix}{stats.skill_id}"
        await self.kv.save(key, stats.model_dump())

    # ---------- 注册与获取 ----------

    async def register_skill(
        self,
        name: str,
        kind: str,
        description: str = "",
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        code_ref: Optional[Dict[str, str]] = None,
        plan_steps: Optional[List[Dict[str, Any]]] = None,
        supersedes: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> SkillDefinition:
        """
        注册一个新的 SkillDefinition。
        v1 不做去重策略，由调用方控制命名。
        """
        skill_id = f"skill_{uuid.uuid4().hex}"
        skill = SkillDefinition(
            skill_id=skill_id,
            name=name,
            kind=kind,
            description=description,
            domain=domain,
            tags=tags or [],
            code_ref=code_ref,
            plan_steps=plan_steps,
            supersedes=supersedes,
            meta=meta or {},
        )

        await self._save_skill(skill)
        await self._save_stats(SkillStats(skill_id=skill_id))

        self.tracer.span(
            "L1",
            "skill_registered",
            module="skills",
            input={
                "skill_id": skill_id,
                "name": name,
                "kind": kind,
                "domain": domain,
            },
        )

        return skill

    async def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        data = await self.kv.get(f"{self.skill_prefix}{skill_id}")
        if not data:
            return None
        return SkillDefinition(**data)

    async def get_skill_by_name(self, name: str) -> Optional[SkillDefinition]:
        skill_id = await self.kv.hget(self.name_index_key, name)
        if not skill_id:
            return None
        return await self.get_skill(skill_id)

    async def list_skills(self, limit: int = 100) -> List[SkillDefinition]:
        ids = await self.kv.get(self.index_key) or []
        ids = list(dict.fromkeys(ids))[-limit:]
        res: List[SkillDefinition] = []
        for sid in ids:
            data = await self.kv.get(f"{self.skill_prefix}{sid}")
            if data:
                res.append(SkillDefinition(**data))
        return res

    # ---------- 统计更新 ----------

    async def get_stats(self, skill_id: str) -> SkillStats:
        data = await self.kv.get(f"{self.stats_prefix}{skill_id}")
        if not data:
            stats = SkillStats(skill_id=skill_id)
            await self._save_stats(stats)
            return stats
        return SkillStats(**data)

    async def update_stats(
        self,
        skill_id: str,
        success: bool,
        latency_sec: float,
    ) -> None:
        stats = await self.get_stats(skill_id)
        stats.calls += 1
        if success:
            stats.success += 1
        else:
            stats.failure += 1

        # 简单移动平均
        if stats.calls == 1:
            stats.avg_latency_sec = latency_sec
        else:
            alpha = 0.2
            stats.avg_latency_sec = (
                alpha * latency_sec + (1 - alpha) * stats.avg_latency_sec
            )

        stats.last_called_at = now_utc()

        await self._save_stats(stats)

        self.tracer.span(
            "L1",
            "skill_stats_updated",
            module="skills",
            input={
                "skill_id": skill_id,
                "success": success,
                "latency_sec": latency_sec,
            },
        )
