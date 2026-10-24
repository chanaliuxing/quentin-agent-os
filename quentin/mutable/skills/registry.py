from typing import List, Optional, Dict
from quentin.kernel.schemas import SkillSpec
from quentin.infra.storage.kv_store import KVStore


class SkillRegistry:
    """
    技能注册中心：
    - 存储系统演化出的 SkillSpec
    - 允许按 domain / tag 检索
    - 未来这里会是 ToolManager 的重要数据源
    """

    def __init__(self, kv_store: KVStore, prefix: str = "skill:"):
        self.kv = kv_store
        self.prefix = prefix

    async def save_skill(self, skill: SkillSpec) -> None:
        key = f"{self.prefix}{skill.skill_id}"
        await self.kv.save(key, skill.model_dump())
        await self.kv.append_list(f"{self.prefix}all", skill.skill_id)

    async def get_skill(self, skill_id: str) -> Optional[SkillSpec]:
        data = await self.kv.get(f"{self.prefix}{skill_id}")
        if data:
            return SkillSpec(**data)
        return None

    async def list_skills(self, domain: Optional[str] = None) -> List[SkillSpec]:
        # v0: 简单遍历，生产环境应使用索引
        all_ids = await self.kv.get(f"{self.prefix}all") or []
        skills = []
        for sid in all_ids:
            s = await self.get_skill(sid)
            if s and (domain is None or s.domain == domain or s.domain == "cross"):
                skills.append(s)
        return skills
