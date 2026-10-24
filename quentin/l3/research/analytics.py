from __future__ import annotations

from typing import Any, Dict
from collections import Counter

from quentin.skills.library import SkillLibrary
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.infra.storage.kv_store import KVStore


class ResearchSummary:
    """
    简单的研究层汇总结果对象（纯 dict 包装，方便 CLI 打印）
    """

    def __init__(self, data: Dict[str, Any]):
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        return self.data


class ResearchAnalytics:
    """
    从技能 / patch / 实验结果中汇总信息，
    给出“最近哪些自改方向最有收益”的粗略结论。
    """

    def __init__(
        self,
        kv_store: KVStore,
        skill_library: SkillLibrary,
        self_programming_engine: SelfProgrammingEngine,
    ):
        self.kv = kv_store
        self.skill_library = skill_library
        self.self_programming_engine = self_programming_engine

    async def summarize(self) -> ResearchSummary:
        skills = await self.skill_library.list_skills(limit=2000)
        stats_by_id = {}
        for s in skills:
            try:
                stats_by_id[s.skill_id] = await self.skill_library.get_stats(s.skill_id)
            except Exception:
                stats_by_id[s.skill_id] = None
        # Get patch reports from SelfProgrammingEngine
        patch_reports = await self.self_programming_engine.list_patch_reports()

        # 1) 技能侧统计
        total_skills = len(skills)
        skill_usage = 0
        for s in skills:
            st = stats_by_id.get(s.skill_id)
            if st is not None:
                skill_usage += int(getattr(st, "calls", 0) or 0)
        high_usage_skills = sorted(
            skills,
            key=lambda s: int(getattr(stats_by_id.get(s.skill_id), "calls", 0) or 0),
            reverse=True,
        )[:5]

        # 2) Patch 侧统计 (using PatchReport)
        total_patches = len(patch_reports)
        status_counter = Counter(p.status.value for p in patch_reports)
        by_module = Counter(p.module_path for p in patch_reports)
        passed_modules = Counter(
            p.module_path for p in patch_reports if p.success
        )

        # 3) 实验结果侧：我们约定 ExperimentResult 存在于 exp_result:* key 下
        #   这里只统计数量，不深挖
        all_keys = await self.kv.list_keys("experiment:cfg:") # list_all for experiments config
        num_experiments = len(all_keys)

        data: Dict[str, Any] = {
            "skills": {
                "total_skills": total_skills,
                "total_usage": skill_usage,
                "top_skills": [
                    {
                        "skill_id": s.skill_id,
                        "name": s.name,
                        "usage": int(getattr(stats_by_id.get(s.skill_id), "calls", 0) or 0),
                        # "avg_success": s.avg_success_rate, # SkillDefinition no longer has avg_success_rate directly
                    }
                    for s in high_usage_skills
                ],
            },
            "patches": {
                "total_patches": total_patches,
                "status_counts": dict(status_counter),
                "top_modules_by_patch_count": by_module.most_common(5),
                "top_modules_by_passed_patches": passed_modules.most_common(5),
            },
            "experiments": {
                "total_experiments": num_experiments,
            },
        }

        # 粗略回答两个问题：
        # Q1: 最近哪几类自改实验最有收益？
        #   用「通过 patch 最多的模块」作为 proxy
        best_modules = passed_modules.most_common(3)
        data["insights"] = {
            "most_improved_modules": [
                {"module": m, "passed_patches": c} for (m, c) in best_modules
            ],
            "comment": (
                "Modules with more passed patches are likely benefiting most "
                "from self-programming experiments."
            ),
        }

        return ResearchSummary(data)
