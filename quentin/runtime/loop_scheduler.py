from __future__ import annotations
from typing import Dict, Any
from pathlib import Path
import json
import logging
from quentin.runtime.agent_runtime import AgentRuntime
from quentin.infra.storage.execution_store import ExecutionStore
from quentin.kernel.schemas import ExecutionSummary
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


class LoopScheduler:
    """
    负责调度：
    - Cognitive Loop: 单个任务执行
    - Immune Loop: 定期检查失败率
    - Sleep Loop: 定期记忆巩固
    - Skill & Code Evolution: 定期发起自改尝试
    """

    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self.exec_store = ExecutionStore(runtime.kv_store)
        self.repo_root = Path(getattr(runtime, "repo_root", ".")).resolve()

    def _append_jsonl(self, rel_path: str, payload: Dict[str, Any]) -> None:
        path = (self.repo_root / rel_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("LoopScheduler: failed to append %s", rel_path)

    async def run_single_task(self, task: Dict[str, Any]) -> ExecutionSummary:
        summary = await self.runtime.cognitive_loop.run_task(task)
        await self.exec_store.save_summary(summary)
        return summary

    async def run_maintenance(self):
        """
        维护任务：可以被 cron / 定时器每 X 分钟调用一次。
        - 把最近的执行结果交给免疫 / 睡眠 / skill evolution / 自编程。
        """
        recent = await self.exec_store.list_recent(limit=200)

        # 1. Immune Loop：异常检测，必要时降级
        await self.runtime.immune_loop.run(recent)

        # 2. Sleep Loop：记忆巩固 & STS 衰减
        await self.runtime.sleep_loop.run(recent)

        # 3. Skill Evolution：挖掘高成功率 Trace → Skill 模式（暂不自动 patch）
        success = [s for s in recent if s.status == "success"]
        skills = await self.runtime.skill_evolution_loop.run(success) if getattr(self.runtime, "skill_evolution_loop", None) else []
        if skills:
            # Persist mined skills for later review / promotion.
            for s in skills:
                self._append_jsonl(
                    "data/skills/mined.jsonl",
                    {"captured_at": now_iso(), "skill": s if isinstance(s, dict) else getattr(s, "to_dict", lambda: str(s))()},
                )
            # Best-effort: register into SkillLibrary if available.
            lib = getattr(self.runtime, "skill_library", None)
            if lib is not None and hasattr(lib, "create_skill"):
                for s in skills:
                    if not isinstance(s, dict):
                        continue
                    try:
                        await lib.create_skill(
                            name=str(s.get("name") or s.get("skill_name") or "mined_skill"),
                            description=str(s.get("description") or ""),
                            domain=str(s.get("domain") or "generic"),
                            pattern_goal=str(s.get("pattern_goal") or s.get("goal") or ""),
                            steps=list(s.get("steps") or []),
                            tags=list(s.get("tags") or []),
                            created_from_task_ids=list(s.get("source_trace_ids") or s.get("created_from_task_ids") or []),
                        )
                    except Exception:
                        logger.exception("LoopScheduler: failed to register mined skill")

        # 4. Self-Programming：从失败中触发 patch 候选
        patches = await self.runtime.self_improvement.propose_patches_from_summaries(
            recent
        )

        # 4.1 Budget & Safety 检查
        if patches and await self.runtime.budget_controller.can_run_experiment():
            # 4.2 PatchRunner 跑测试（只在 sandbox/staging）
            patches = await self.runtime.patch_runner.run_patches(patches)
            await self.runtime.budget_controller.record_run()

            # 4.3 Evolution Strategy: 选出真正值得保留的 patch（目前先全部通过即可）
            approved = await self.runtime.evolution_strategy.choose_best_patch(patches)
            if approved:
                for p in approved if isinstance(approved, list) else [approved]:
                    self._append_jsonl(
                        "data/patches/approved.jsonl",
                        {
                            "approved_at": now_iso(),
                            "patch": p if isinstance(p, dict) else getattr(p, "to_dict", lambda: str(p))(),
                        },
                    )
        
        # 5. Blueprint Improvement Loop：周期性检查蓝皮书差距并生成改进计划
        # 只有当 Research Layer 已经挂载时才运行
        if self.runtime.research_layer and self.runtime.blueprint_improver:
            # 使用一个简单的 ResearchRequest 占位符
            dummy_research_request = {
                "id": f"maint-{now_iso()}",
                "strategy": "auto_maintenance"
            }
            
            blueprint_result = self.runtime.run_blueprint_improvement_cycle(
                max_gaps=3, 
                research_request=dummy_research_request
            )
            # 这里可以记录 blueprint_result 到日志或 metrics
            
        # 全流程完成
