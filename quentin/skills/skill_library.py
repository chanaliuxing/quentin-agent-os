from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, UTC

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.kernel.schemas import SkillDefinition, SkillStatus


@dataclass
class SkillLibrary:
    """
    负责：
    - 持久化 SkillDefinition
    - 记录使用次数
    - 简单地根据 goal 做匹配（后面可以换成向量检索）
    """
    kv: KVStore
    tracer: Tracer
    prefix: str = "skill:"

    def _key(self, sid: str) -> str:
        return f"{self.prefix}{sid}"

    async def save_skill(self, skill: SkillDefinition) -> None:
        skill.updated_at = datetime.now(UTC) # Ensure updated_at is always current on save
        await self.kv.save(self._key(skill.skill_id), skill.model_dump())
        all_ids = await self.kv.get(f"{self.prefix}all") or []
        if skill.skill_id not in all_ids:
            all_ids.append(skill.skill_id)
            await self.kv.save(f"{self.prefix}all", all_ids)

        self.tracer.span(
            "L2",
            "skill_save",
            module="skill_library",
            input={"skill_id": skill.skill_id, "name": skill.name},
        )

    async def create_skill(
        self,
        name: str,
        description: str,
        domain: str,
        pattern_goal: str,
        steps: List[Dict[str, Any]],
        tags: Optional[List[str]] = None,
        created_from_task_ids: Optional[List[str]] = None,
        status: SkillStatus = SkillStatus.draft,
    ) -> SkillDefinition:
        sid = f"skill_{uuid.uuid4().hex}"
        skill = SkillDefinition(
            skill_id=sid,
            name=name,
            description=description,
            domain=domain,
            pattern_goal=pattern_goal,
            steps=steps,
            tags=tags or [],
            created_from_task_ids=created_from_task_ids or [],
            status=status,
            stats={"use_count": 0},
        )
        await self.save_skill(skill)
        return skill

    async def get(self, skill_id: str) -> Optional[SkillDefinition]:
        data = await self.kv.get(self._key(skill_id))
        if not data:
            return None
        return SkillDefinition(**data)

    async def list_all(self) -> List[SkillDefinition]:
        ids = await self.kv.get(f"{self.prefix}all") or []
        ids = list(dict.fromkeys(ids))
        res: List[SkillDefinition] = []
        for sid in ids:
            data = await self.kv.get(self._key(sid))
            if not data:
                continue
            res.append(SkillDefinition(**data))
        return res

    async def record_usage(self, skill_id: str) -> None:
        skill = await self.get(skill_id)
        if not skill:
            return
        use_count = int(skill.stats.get("use_count", 0)) + 1
        skill.stats["use_count"] = use_count
        await self.save_skill(skill)

    async def find_for_goal(
        self,
        goal: str,
        domain: str = "generic",
        top_k: int = 3,
    ) -> List[SkillDefinition]:
        """
        极简 goal 匹配策略：
        - 同 domain 优先
        - pattern_goal 与当前 goal 的字符交集/长度 作为相似度
        - 只返回 status=active 的技能
        """
        all_skills = await self.list_all()
        candidates: List[tuple[float, SkillDefinition]] = []

        g = goal.lower()
        primary: List[tuple[float, SkillDefinition]] = []
        secondary: List[tuple[float, SkillDefinition]] = []

        for s in all_skills:
            if s.status != SkillStatus.active:
                continue

            score = 0.0
            pg = (s.pattern_goal or "").lower()
            if not pg:
                continue

            # 简单的字符级重叠度
            common = set(g.split()) & set(pg.split())
            score = len(common) / max(1, len(set(pg.split())))

            # 同域加一点分（cross 不加分，但也不扣分）
            if s.domain == domain:
                score += 0.1

            if score > 0.0:
                # Primary pool: same-domain + cross-domain skills.
                if s.domain in (domain, "cross"):
                    primary.append((score, s))
                else:
                    # Secondary pool: other domains (allowed as a fallback when we don't have enough hits).
                    secondary.append((score * 0.5, s))

        primary.sort(key=lambda x: x[0], reverse=True)
        out: List[SkillDefinition] = [s for _, s in primary[:top_k]]

        if len(out) < top_k and secondary:
            secondary.sort(key=lambda x: x[0], reverse=True)
            seen = {s.skill_id for s in out}
            for _score, s in secondary:
                if s.skill_id in seen:
                    continue
                out.append(s)
                seen.add(s.skill_id)
                if len(out) >= top_k:
                    break

        return out
