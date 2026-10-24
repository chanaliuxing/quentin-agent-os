# meta_agent/immune/runner.py
from __future__ import annotations
from typing import List
from pathlib import Path
import json

from meta_agent.monitoring.status_snapshot import build_status_snapshot
from meta_agent.immune.detector import detect_cases_from_snapshot
from meta_agent.immune.planner import plan_immune_actions
from meta_agent.immune.models import ImmuneCase, ImmuneAction, ImmuneActionKind
from meta_agent.skills.registry import SkillRegistry, SkillStatus
from meta_agent.tracing import JsonlTraceRecorder

trace_recorder = JsonlTraceRecorder(repo_root=".")
skill_registry = SkillRegistry()

def _apply_action(action: ImmuneAction) -> None:
    """
    v1: 只实现一部分简单动作，其他动作先 log。
    以后可以扩展为：
      - 写 feature_flags JSON
      - 动态调整 orchestrator 的 budget
      - 调用 PatchRegistry 等
    """
    trace_recorder.log_event(
        event_type="immune_action_apply_start",
        payload=action.__dict__,
    )

    if action.kind == ImmuneActionKind.NO_OP:
        # 纯记录，不做事
        return

    # Skill 相关动作
    if action.kind in (ImmuneActionKind.DISABLE_SKILL, ImmuneActionKind.DOWNGRADE_SKILL):
        if not action.target_id:
            return
        skill = skill_registry.get(action.target_id)
        if not skill:
            return

        # v1：用 DEPRECATED 当作“禁用/降级”状态
        new_status = SkillStatus.DEPRECATED
        skill_registry.update_status(skill.id, new_status)
        trace_recorder.log_event(
            event_type="immune_action_skill_updated",
            payload={
                "skill_id": skill.id,
                "new_status": new_status.value,
                "reason": action.reason,
            },
        )
        return

    # PAUSE_AUTOPATCH：写一个 feature flag 文件，后续自编程流水线可以读取
    if action.kind == ImmuneActionKind.PAUSE_AUTOPATCH:
        flag_path = Path("data/feature_flags/auto_patch_disabled.json")
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(
            json.dumps(
                {
                    "disabled": True,
                    "reason": action.reason,
                    "case_id": action.case_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        trace_recorder.log_event(
            event_type="immune_action_flag_written",
            payload={
                "flag": str(flag_path),
                "reason": action.reason,
            },
        )
        return

    # REDUCE_TASK_BUDGET：写一个 orchestrator 配置文件，后续可以接进去
    if action.kind == ImmuneActionKind.REDUCE_TASK_BUDGET:
        target = action.target_id or "global"
        reduce_factor = action.params.get("reduce_factor", 0.5)
        cfg_path = Path("data/immune/orchestrator_budget_overrides.json")
        cfg_path.parent.mkdir(parents=True, exist_ok=True)

        # 合并更新
        existing = {}
        if cfg_path.exists():
            try:
                existing = json.loads(cfg_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                existing = {}

        existing[target] = {
            "reduce_factor": reduce_factor,
            "case_id": action.case_id,
            "reason": action.reason,
        }

        cfg_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        trace_recorder.log_event(
            event_type="immune_action_budget_override",
            payload={
                "target": target,
                "reduce_factor": reduce_factor,
            },
        )
        return

    # REQUEST_HUMAN_REVIEW / BLACKLIST_PATCH / PAUSE_TASK 先只做 log
    trace_recorder.log_event(
        event_type="immune_action_not_implemented",
        payload=action.__dict__,
    )

def run_immune_cycle(window_hours: int = 24) -> None:
    """
    ImmuneLoop v2：
      1. 读取最近 window_hours 的状态快照
      2. 检测异常 → ImmuneCase
      3. 对每个 case 规划 ImmuneAction（heuristic + council 精修）
      4. 执行这些动作（写 feature_flags / 更新 skill 状态 等）
    """
    snapshot = build_status_snapshot(window_hours=window_hours)

    cases: List[ImmuneCase] = detect_cases_from_snapshot(snapshot)
    if not cases:
        trace_recorder.log_event(
            event_type="immune_cycle_no_cases",
            payload={"window_hours": window_hours},
        )
        return

    actions: List[ImmuneAction] = plan_immune_actions(cases)
    trace_recorder.log_event(
        event_type="immune_cycle_planned",
        payload={
            "window_hours": window_hours,
            "num_cases": len(cases),
            "num_actions": len(actions),
        },
    )

    for a in actions:
        _apply_action(a)

    trace_recorder.log_event(
        event_type="immune_cycle_done",
        payload={
            "window_hours": window_hours,
            "num_cases": len(cases),
            "num_actions": len(actions),
        },
    )
