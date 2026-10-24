from __future__ import annotations
from typing import List
from pathlib import Path
import logging

from quentin.skills.registry import SkillRegistry, SkillStatus
from quentin.self_programming.skill_impl_orchestrator import (
    build_skill_impl_context,
    generate_skill_impl_patch,
)
from quentin.self_programming.skill_evaluator import SkillPatchEvaluator
from meta_agent.patches.safe_applier import SafePatchApplier
from quentin.governance.patch_council import PatchGovernanceCouncil
from meta_agent.config.feature_flags import feature_flags
from quentin.traces.core import JsonlTraceRecorder
from quentin.memory.fabric import MemoryFabric
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.l3.research.experiments import ExperimentOrchestrator
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)

def _select_candidate_skills(skill_registry: SkillRegistry, domain: str, max_skills: int = 3) -> List[str]:
    """
    策略 v1：
      - 选本 domain 下 status = DRAFT
      - 有 stub，但还没实现（文件里还带 NotImplementedError 或 placeholder 标记）
    这里只挑 skill_id，真正检查 stub 内容在 build_skill_impl_context 里做。
    """
    skills = skill_registry.list_skills(domain=domain, status=SkillStatus.DRAFT)
    # 简单按创建时间排序，挑前几条
    skills = sorted(skills, key=lambda s: s.created_at)[:max_skills]
    return [s.id for s in skills]

def run_skill_impl_cycle(
    repo_root: Path,
    skill_registry: SkillRegistry,
    memory_fabric: MemoryFabric,
    engine: SelfProgrammingEngine,
    evaluator: PatchEvaluator,
    applier: SafePatchApplier,
    govern_council: PatchGovernanceCouncil,
    trace_recorder: JsonlTraceRecorder,
    domain: str,
    max_skills: int = 2,
) -> None:
    """
    一次自编程周期：
    1. 挑选候选技能
    2. 为每个技能生成 patch proposal
    3. 调 PatchEvaluator 跑测试
    4. 调 PatchGovernanceCouncil 做决策
    5. 通过的 patch 应用到 repo，并把 Skill 状态改为 ACTIVE（或待人工确认）
    """
    candidate_ids = _select_candidate_skills(skill_registry, domain=domain, max_skills=max_skills)
    if not candidate_ids:
        trace_recorder.record_event(
            event_type="skill_impl_no_candidates",
            payload={"domain": domain},
        )
        return

    for sid in candidate_ids:
        skill = skill_registry.get(sid)
        if not skill:
            continue

        ctx = build_skill_impl_context(skill, repo_root, memory_fabric)
        if not ctx:
            continue

        trace_recorder.record_event(
            event_type="skill_impl_start",
            payload={"skill_id": sid, "skill_name": skill.name, "domain": domain},
        )

        # 1) 生成 patch proposal + diff
        proposal = generate_skill_impl_patch(engine, trace_recorder, ctx)

        if not proposal:
            logger.error(f"Failed to generate patch proposal for skill {sid}")
            continue

        # 2) PatchEvaluator：跑测试/实验
        report = evaluator.evaluate(patch=proposal)

        trace_recorder.record_event(
            event_type="skill_impl_evaluated",
            payload={
                "skill_id": sid,
                "proposal_id": proposal.id,
                "metrics": report.metrics,
                "status": report.status.value,
            },
        )

        # 3) 交给 PatchGovernanceCouncil 决定 （自动 or 半自动）
        decision = govern_council.decide_on_patch(proposal, report)

        trace_recorder.record_event(
            event_type="skill_impl_governed",
            payload={
                "skill_id": sid,
                "proposal_id": proposal.id,
                "decision": decision.action.value,
                "reason": decision.reason,
            },
        )

        if not decision.should_apply:
            # 这次 patch 被拒绝，可记录为 ImmuneCase，留待下一轮改进
            continue

        # 👇 新增：尊重 auto_patch 开关
        auto_patch = feature_flags.get_auto_patch_flag()
        if not auto_patch.enabled:
            trace_recorder.record_event(
                event_type="skill_impl_autopatch_disabled",
                payload={
                    "skill_id": sid,
                    "patch_id": proposal.id,
                    "reason": auto_patch.reason,
                    "case_id": auto_patch.case_id,
                },
            )
            # 不自动 apply，但可以把 patch 标记成 "AWAITING_MANUAL_APPLY"
            skill_registry.update_status(skill.id, SkillStatus.DRAFT)
            continue

        # 4) 通过安全内核应用 patch
        safety_result = applier.apply_patch(proposal)

        if safety_result.is_blocked:
            # patch 虽然 governance 决定可以，但安全内核阻断了
            trace_recorder.record_event(
                event_type="skill_impl_blocked_by_safety",
                payload={
                    "skill_id": sid,
                    "patch_id": proposal.id,
                    "reasons": safety_result.reasons,
                },
            )
            # 不更新 Skill 状态，保持 DRAFT
            continue

        # 5) 更新 Skill 状态：根据策略可直接 ACTIVE，或标记为 "awaiting_review"
        new_status = SkillStatus.ACTIVE if decision.auto_approve else SkillStatus.DRAFT
        skill_registry.update_status(skill.id, new_status)

        trace_recorder.record_event(
            event_type="skill_impl_applied",
            payload={
                "skill_id": sid,
                "proposal_id": proposal.id,
                "new_status": new_status.value,
                "ts": now_iso(),
            },
        )
