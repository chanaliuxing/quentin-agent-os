from __future__ import annotations

"""CognitiveLoop runtime/planner shim bindings.

This module holds method bindings for planner/executor/maintenance/reflection
helpers that are mounted onto `CognitiveLoop` at import time.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta_agent.config.feature_flags import (
    PROMPT_MIGRATION_M1_SYSTEM_FACTORY,
    PROMPT_MIGRATION_M3_SYSTEM_EVENTS,
    feature_flags,
)
from quentin.cognitive.loop_executor import run_executor as executor_run_executor
from quentin.cognitive.loop_goal_flow import (
    gist_memory_context as goal_flow_gist_memory_context,
    procedural_memory_context as goal_flow_procedural_memory_context,
    run_planner_or_custom as goal_flow_run_planner_or_custom,
)
from quentin.cognitive.loop_maintenance import (
    apply_immune_action as maintenance_apply_immune_action,
    flush_memory as maintenance_flush_memory,
    write_memory as maintenance_write_memory,
    write_trace as maintenance_write_trace,
)
from quentin.cognitive.loop_entrypoints import check_context_and_flush as entry_check_context_and_flush
from quentin.cognitive.loop_metrics import (
    extract_attempt_metrics as metrics_extract_attempt_metrics,
    recent_forbidden_actions as metrics_recent_forbidden_actions,
)
from quentin.cognitive.loop_misc import (
    build_planner_result_from_reflection as misc_build_planner_result_from_reflection,
    cache_plan_override as misc_cache_plan_override,
    enqueue_skill_ideas_from_reflection as misc_enqueue_skill_ideas_from_reflection,
    get_plan_override_if_any as misc_get_plan_override_if_any,
    prune_context_for_focus as misc_prune_context_for_focus,
    should_trigger_reflection as misc_should_trigger_reflection,
    strict_reason_hint_from_env as misc_strict_reason_hint_from_env,
    strict_reason_list_from_env as misc_strict_reason_list_from_env,
)
from quentin.cognitive.loop_models import CognitiveTask, PlannerResult
from quentin.cognitive.loop_plan_guards import (
    apply_self_awareness_runtime_controls,
    assess_discovery_guard,
    build_antipattern_recovery_plan,
    build_planner_fallback_steps,
    detect_execution_antipattern,
    extract_interactive_target_path,
    has_meaningful_progress,
    is_discovery_step,
    is_risky_step,
    is_tool_only_no_update,
    repair_plan_quality,
    update_circuit_breaker_state,
)
from quentin.cognitive.loop_planner import (
    build_executor_prompt_context as planner_build_executor_prompt_context,
    build_planner_hints as planner_build_planner_hints,
    build_planner_question_prompt as planner_build_planner_question_prompt,
    run_planner as planner_run_planner,
)
from quentin.cognitive.loop_runtime_helpers import (
    drain_system_events_for_planner as runtime_drain_system_events_for_planner,
    emit_self_awareness_event as runtime_emit_self_awareness_event,
)
from quentin.goals.schema import GoalSpec
from quentin.immune.loop import ImmuneAction

logger = logging.getLogger(__name__)


class _LoopHintsAdapter:
    @staticmethod
    def _strict_reason_hint_from_env() -> str:
        return misc_strict_reason_hint_from_env()


def _run_checkpoint(self, task_id: str, loop_idx: int, metrics: Dict[str, Any]):
    from quentin.infra.sessions.checkpoint import checkpoint_manager

    checkpoint_manager.save_checkpoint(task_id, {"loop_idx": loop_idx, "metrics": metrics})


def _run_planner_or_custom(self, task: CognitiveTask, goal: GoalSpec, extra_ctx: Optional[Dict[str, Any]] = None) -> PlannerResult:
    return goal_flow_run_planner_or_custom(
        self,
        planner_result_cls=PlannerResult,
        task=task,
        goal=goal,
        extra_ctx=extra_ctx,
    )


def _procedural_memory_context(self, *, task: CognitiveTask, goal: GoalSpec) -> Dict[str, Any]:
    return goal_flow_procedural_memory_context(self, task=task, goal=goal)


def _gist_memory_context(self, *, task: CognitiveTask, goal: GoalSpec) -> Dict[str, Any]:
    return goal_flow_gist_memory_context(self, task=task, goal=goal)


def _extract_attempt_metrics(*, raw_exec_data: Dict[str, Any], attempt_start: datetime | str, attempt_end: datetime | str) -> Dict[str, Any]:
    return metrics_extract_attempt_metrics(
        raw_exec_data=raw_exec_data,
        attempt_start=attempt_start,
        attempt_end=attempt_end,
    )


def _write_trace(
    self,
    *,
    trace_id: str,
    task: CognitiveTask,
    goal: GoalSpec,
    plan_summary: str,
    actions_summary: str,
    final_output: str,
    done_result: Optional[Any],
    start_ts: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    _ = (plan_summary, actions_summary, final_output)
    return maintenance_write_trace(
        self,
        trace_id=trace_id,
        task=task,
        goal=goal,
        done_result=done_result,
        start_ts=start_ts,
        metrics=metrics,
    )


def _write_memory(
    self,
    *,
    task: CognitiveTask,
    goal: GoalSpec,
    plan_summary: str,
    actions_summary: str,
    final_output: str,
    done_result: Optional[Any],
) -> None:
    _ = goal
    return maintenance_write_memory(
        self,
        task=task,
        final_output=final_output,
        plan_summary=plan_summary,
        actions_summary=actions_summary,
        done_result=done_result,
    )


def _apply_immune_action(self, action: ImmuneAction, goal: GoalSpec) -> None:
    return maintenance_apply_immune_action(self, action=action, goal=goal)


def _emit_self_awareness_event(self, *, session_id: str, goal: GoalSpec, attempt_index: int, snapshot: Any) -> None:
    return runtime_emit_self_awareness_event(
        self,
        session_id=session_id,
        goal=goal,
        attempt_index=attempt_index,
        snapshot=snapshot,
    )


async def _check_context_and_flush(self, goal: GoalSpec, metrics: Dict[str, Any], session_id: str) -> None:
    return await entry_check_context_and_flush(self, goal=goal, metrics=metrics, session_id=session_id)


async def _flush_memory(self, goal: GoalSpec, session_id: str) -> None:
    return await maintenance_flush_memory(self, goal=goal, session_id=session_id)


def _ensure_goal(self, task: CognitiveTask) -> GoalSpec:
    existing = self.goal_manager.get_latest_goal_for_task(task.task_id)
    if existing:
        logger.info("CognitiveLoop: Resuming existing goal %s for task %s", existing.goal_id, task.task_id)
        return existing
    return self.goal_manager.create_and_save_goal(**task.to_goal_spec())


def _run_planner(self, goal: GoalSpec, context: Dict[str, Any]) -> PlannerResult:
    payload = planner_run_planner(self, goal, context or {})
    return PlannerResult(
        goal_id=str(payload.get("goal_id") or goal.goal_id),
        raw_output=str(payload.get("raw_output") or ""),
        steps=list(payload.get("steps") or []),
        used_skills=list(payload.get("used_skills") or []),
    )


async def _run_executor(
    self,
    task: CognitiveTask,
    goal: GoalSpec,
    plan_summary: str,
    *,
    progressive_pressure: bool = False,
    self_awareness: Optional[Any] = None,
) -> Dict[str, Any]:
    return await executor_run_executor(
        self,
        task=task,
        goal=goal,
        plan_summary=plan_summary,
        progressive_pressure=progressive_pressure,
        self_awareness=self_awareness,
    )


def _prompt_factory_enabled() -> bool:
    return feature_flags.is_prompt_migration_enabled(PROMPT_MIGRATION_M1_SYSTEM_FACTORY, default=False)


def _system_events_enabled() -> bool:
    return feature_flags.is_prompt_migration_enabled(PROMPT_MIGRATION_M3_SYSTEM_EVENTS, default=False)


def _drain_system_events_for_planner(self, *, session_id: str) -> str:
    return runtime_drain_system_events_for_planner(self, session_id=session_id)


def _prune_context_for_focus(self, context: Dict[str, Any], iteration: int) -> Dict[str, Any]:
    return misc_prune_context_for_focus(context=context, iteration=iteration)


def _build_planner_question_prompt(
    self,
    *,
    goal: GoalSpec,
    task_text: str,
    plan_schema_text: str,
    skill_suggestions: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    return planner_build_planner_question_prompt(
        self,
        goal=goal,
        task_text=task_text,
        plan_schema_text=plan_schema_text,
        skill_suggestions=skill_suggestions,
        context=context,
    )


def _build_executor_prompt_context(self, *, task: CognitiveTask, goal: GoalSpec, progressive_pressure: bool) -> Dict[str, Any]:
    return planner_build_executor_prompt_context(
        self,
        task=task,
        goal=goal,
        progressive_pressure=progressive_pressure,
    )


async def _run_executor_or_custom(self, task: CognitiveTask, goal: GoalSpec, plan_summary: str, **kwargs: Any) -> Dict[str, Any]:
    return await self._run_executor(task, goal, plan_summary, **kwargs)


def _build_planner_hints(context: Optional[Dict[str, Any]]) -> List[str]:
    return planner_build_planner_hints(_LoopHintsAdapter, context)


def _strict_reason_hint_from_env() -> str:
    return misc_strict_reason_hint_from_env()


def _strict_reason_list_from_env() -> List[str]:
    return misc_strict_reason_list_from_env()


def _recent_forbidden_actions(self, *, limit: int = 6) -> List[str]:
    return metrics_recent_forbidden_actions(repo_root=self.repo_root, limit=limit)


def _build_planner_fallback_steps(*, task_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return build_planner_fallback_steps(task_text=task_text, context=context)


def _update_circuit_breaker_state(*, raw_error: Any, consecutive_errors: int, last_error_msg: str, threshold: int = 2) -> tuple[int, str, str, bool]:
    return update_circuit_breaker_state(
        raw_error=raw_error,
        consecutive_errors=consecutive_errors,
        last_error_msg=last_error_msg,
        threshold=threshold,
    )


def _assess_discovery_guard(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return assess_discovery_guard(steps)


def _repair_plan_quality(self, *, task_text: str, context: Dict[str, Any], steps: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    return repair_plan_quality(task_text=task_text, context=context, steps=steps)


def _should_trigger_reflection(self, goal: GoalSpec, metrics: Dict[str, Any], failure_count: int) -> bool:
    _ = (goal, metrics)
    return misc_should_trigger_reflection(failure_count=failure_count, metrics=metrics)


def _build_planner_result_from_reflection(self, goal: GoalSpec, plan_obj: Dict[str, Any]) -> PlannerResult:
    return misc_build_planner_result_from_reflection(planner_result_cls=PlannerResult, goal=goal, plan_obj=plan_obj)


def _cache_plan_override(self, goal: GoalSpec, plan_obj: Dict[str, Any]) -> None:
    return misc_cache_plan_override(loop=self, goal=goal, plan_obj=plan_obj)


def _get_plan_override_if_any(self, goal: GoalSpec) -> Optional[Dict[str, Any]]:
    return misc_get_plan_override_if_any(loop=self, goal=goal)


def _enqueue_skill_ideas_from_reflection(self, goal: GoalSpec, ideas: List[Dict[str, Any]]) -> None:
    return misc_enqueue_skill_ideas_from_reflection(loop=self, goal=goal, ideas=ideas, logger=logger)


def _record_reflection(self, goal: GoalSpec, execution_summary: Dict[str, Any], advice: Any) -> None:
    _ = (goal, execution_summary, advice)
    try:
        if self.traces_store:
            pass
    except Exception:
        logger.exception("CognitiveLoop: failed to record reflection.")


def install_loop_tail_shims(loop_cls: type) -> None:
    """Install runtime/planner/helper wrappers onto `CognitiveLoop`."""
    loop_cls._run_checkpoint = _run_checkpoint
    loop_cls._run_planner_or_custom = _run_planner_or_custom
    loop_cls._procedural_memory_context = _procedural_memory_context
    loop_cls._gist_memory_context = _gist_memory_context
    loop_cls._extract_attempt_metrics = staticmethod(_extract_attempt_metrics)
    loop_cls._write_trace = _write_trace
    loop_cls._write_memory = _write_memory
    loop_cls._apply_immune_action = _apply_immune_action
    loop_cls._emit_self_awareness_event = _emit_self_awareness_event
    loop_cls._check_context_and_flush = _check_context_and_flush
    loop_cls._flush_memory = _flush_memory
    loop_cls._ensure_goal = _ensure_goal
    loop_cls._run_planner = _run_planner
    loop_cls._run_executor = _run_executor
    loop_cls._prompt_factory_enabled = staticmethod(_prompt_factory_enabled)
    loop_cls._system_events_enabled = staticmethod(_system_events_enabled)
    loop_cls._drain_system_events_for_planner = _drain_system_events_for_planner
    loop_cls._prune_context_for_focus = _prune_context_for_focus
    loop_cls._build_planner_question_prompt = _build_planner_question_prompt
    loop_cls._build_executor_prompt_context = _build_executor_prompt_context
    loop_cls._run_executor_or_custom = _run_executor_or_custom
    loop_cls._build_planner_hints = staticmethod(_build_planner_hints)
    loop_cls._strict_reason_hint_from_env = staticmethod(_strict_reason_hint_from_env)
    loop_cls._strict_reason_list_from_env = staticmethod(_strict_reason_list_from_env)
    loop_cls._recent_forbidden_actions = _recent_forbidden_actions
    loop_cls._build_planner_fallback_steps = staticmethod(_build_planner_fallback_steps)
    loop_cls._update_circuit_breaker_state = staticmethod(_update_circuit_breaker_state)
    loop_cls._assess_discovery_guard = _assess_discovery_guard
    loop_cls._is_discovery_step = staticmethod(is_discovery_step)
    loop_cls._is_risky_step = staticmethod(is_risky_step)
    loop_cls._repair_plan_quality = _repair_plan_quality
    loop_cls._apply_self_awareness_runtime_controls = staticmethod(apply_self_awareness_runtime_controls)
    loop_cls._detect_execution_antipattern = staticmethod(detect_execution_antipattern)
    loop_cls._extract_interactive_target_path = staticmethod(extract_interactive_target_path)
    loop_cls._build_antipattern_recovery_plan = staticmethod(build_antipattern_recovery_plan)
    loop_cls._has_meaningful_progress = staticmethod(has_meaningful_progress)
    loop_cls._is_tool_only_no_update = staticmethod(is_tool_only_no_update)
    loop_cls._should_trigger_reflection = _should_trigger_reflection
    loop_cls._build_planner_result_from_reflection = _build_planner_result_from_reflection
    loop_cls._cache_plan_override = _cache_plan_override
    loop_cls._get_plan_override_if_any = _get_plan_override_if_any
    loop_cls._enqueue_skill_ideas_from_reflection = _enqueue_skill_ideas_from_reflection
    loop_cls._record_reflection = _record_reflection


__all__ = ["install_loop_tail_shims"]
