from __future__ import annotations

"""CognitiveLoop API-side shim bindings.

This module contains thin wrappers used by `CognitiveLoop` for entrypoint/runtime
coordination. It is intentionally lightweight and behavior-preserving.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from quentin.goals.schema import GoalSpec
from quentin.cognitive.loop_context_helpers import (
    compact_last_execution_for_planner as ctx_compact_last_execution_for_planner,
    generate_sensing_report as ctx_generate_sensing_report,
    get_candidate_files as ctx_get_candidate_files,
)
from quentin.cognitive.loop_entrypoints import (
    collect_runtime_perception as entry_collect_runtime_perception,
    try_reflex_plan_from_perception as entry_try_reflex_plan_from_perception,
)
from quentin.cognitive.loop_goal_flow import (
    run_goal_internal as goal_flow_run_goal_internal,
    summarize_history as goal_flow_summarize_history,
)
from quentin.cognitive.loop_misc import (
    apply_attention_context as misc_apply_attention_context,
    build_effective_planner_context as misc_build_effective_planner_context,
    sanitize_executor_output as misc_sanitize_executor_output,
    update_task_from_perception_snapshot as misc_update_task_from_perception_snapshot,
)
from quentin.cognitive.loop_models import CognitiveResult, CognitiveTask, PlannerResult
from quentin.cognitive.loop_orchestration import (
    LoopRuntimeState,
    PreparedRunContext,
    apply_feedback_to_runtime_state as orch_apply_feedback_to_runtime_state,
    check_cognitive_fingerprint_hit as orch_check_cognitive_fingerprint_hit,
    collect_historical_goal_context as orch_collect_historical_goal_context,
    evaluate_attempt_outcome as orch_evaluate_attempt_outcome,
    extract_planner_trace_signals as orch_extract_planner_trace_signals,
    finalize_goal_result as orch_finalize_goal_result,
    handle_attempt_execution_and_feedback as orch_handle_attempt_execution_and_feedback,
    prepare_run_context as orch_prepare_run_context,
    record_capability_gaps as orch_record_capability_gaps,
    record_planning_attempt as orch_record_planning_attempt,
    run_proactive_perception_and_contract as orch_run_proactive_perception_and_contract,
    run_semantic_presensing_short_circuit as orch_run_semantic_presensing_short_circuit,
    run_single_attempt as orch_run_single_attempt,
    warmup_task_runtime as orch_warmup_task_runtime,
)
from quentin.cognitive.loop_runtime_context import (
    compute_plan_for_attempt as runtime_compute_plan_for_attempt,
    get_environment_snapshot as runtime_get_environment_snapshot,
)
from quentin.cognitive.loop_runtime_helpers import (
    build_base_planner_context as runtime_build_base_planner_context,
    infer_focus_paths_from_last_execution as runtime_infer_focus_paths_from_last_execution,
    infer_pre_sensing_focus_paths as runtime_infer_pre_sensing_focus_paths,
    refresh_planner_environment_snapshot as runtime_refresh_planner_environment_snapshot,
)
from quentin.cognitive.self_awareness import SelfAwarenessSnapshot

if TYPE_CHECKING:
    from quentin.cognitive.perception.schemas import PerceptionSnapshot

logger = logging.getLogger(__name__)

try:
    from quentin.skills.miner import SkillMiner  # type: ignore
except Exception:  # noqa: BLE001
    SkillMiner = None  # type: ignore[assignment]


def _generate_sensing_report(self, task: CognitiveTask, focus_paths: List[str]) -> Dict[str, Any]:
    return ctx_generate_sensing_report(repo_root=self.repo_root, task=task, focus_paths=focus_paths)


def _get_environment_snapshot(
    self,
    *,
    focus_paths: Optional[List[str]] = None,
    focused_only: bool = False,
    max_lines: int = 300,
    task: Optional[CognitiveTask] = None,
) -> str:
    return runtime_get_environment_snapshot(
        self,
        focus_paths=focus_paths,
        focused_only=focused_only,
        max_lines=max_lines,
        task=task,
    )


def _infer_pre_sensing_focus_paths(self, task: CognitiveTask) -> List[str]:
    return runtime_infer_pre_sensing_focus_paths(repo_root=self.repo_root, task=task)


def _get_candidate_files(self, task_text: str, *, max_files: int = 12) -> List[str]:
    return ctx_get_candidate_files(repo_root=self.repo_root, task_text=task_text, max_files=max_files)


async def _summarize_history(self, memories: List[Any], goal_id: str) -> str:
    return await goal_flow_summarize_history(self, memories=memories, goal_id=goal_id)


async def _collect_runtime_perception(self, task: CognitiveTask) -> Dict[str, Any]:
    return await entry_collect_runtime_perception(task=task)


def _refresh_planner_environment_snapshot(
    self,
    *,
    task: CognitiveTask,
    last_exec_result: Dict[str, Any],
) -> tuple[str, List[str]]:
    return runtime_refresh_planner_environment_snapshot(self, task=task, last_exec_result=last_exec_result)


def _build_base_planner_context(
    self,
    *,
    task: CognitiveTask,
    historical_context: str,
    env_snapshot: str,
    focus_paths_for_planner: List[str],
    last_exec_result: Dict[str, Any],
    last_plan_result: Optional[PlannerResult],
    latest_self_awareness: SelfAwarenessSnapshot,
    perception_data: Dict[str, Any],
    event_hint: str,
    forbidden_actions: List[str],
    critical_instruction: str = "",
    attempt_index: int = 1,
    failure_count: int = 0,
    tool_only_no_update_count: int = 0,
    retry_budget_remaining: float = 0.0,
    interrupt_cooldown_remaining: int = 0,
) -> Dict[str, Any]:
    return runtime_build_base_planner_context(
        self,
        task=task,
        historical_context=historical_context,
        env_snapshot=env_snapshot,
        focus_paths_for_planner=focus_paths_for_planner,
        last_exec_result=last_exec_result,
        last_plan_result=last_plan_result,
        latest_self_awareness=latest_self_awareness,
        perception_data=perception_data,
        event_hint=event_hint,
        forbidden_actions=forbidden_actions,
        critical_instruction=critical_instruction,
        attempt_index=attempt_index,
        failure_count=failure_count,
        tool_only_no_update_count=tool_only_no_update_count,
        retry_budget_remaining=retry_budget_remaining,
        interrupt_cooldown_remaining=interrupt_cooldown_remaining,
    )


def _build_effective_planner_context(
    self,
    *,
    task: CognitiveTask,
    planner_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    return misc_build_effective_planner_context(task=task, planner_ctx=planner_ctx)


def _update_task_from_perception_snapshot(
    self,
    *,
    task: CognitiveTask,
    perception_snapshot: "PerceptionSnapshot",
) -> None:
    return misc_update_task_from_perception_snapshot(task=task, perception_snapshot=perception_snapshot)


def _apply_attention_context(
    self,
    *,
    planner_ctx: Dict[str, Any],
    perception_snapshot: Optional["PerceptionSnapshot"],
) -> Dict[str, Any]:
    return misc_apply_attention_context(loop=self, planner_ctx=planner_ctx, perception_snapshot=perception_snapshot)


def _try_reflex_plan_from_perception(
    self,
    *,
    task: CognitiveTask,
    goal: GoalSpec,
    effective_ctx: Dict[str, Any],
    perception_snapshot: Optional["PerceptionSnapshot"],
    trace_id: str,
    attempt_index: int,
) -> Optional[PlannerResult]:
    return entry_try_reflex_plan_from_perception(
        self,
        planner_result_cls=PlannerResult,
        task=task,
        goal=goal,
        effective_ctx=effective_ctx,
        perception_snapshot=perception_snapshot,
        trace_id=trace_id,
        attempt_index=attempt_index,
    )


def _sanitize_executor_output(self, exec_res: Dict[str, Any]) -> tuple[str, str]:
    return misc_sanitize_executor_output(loop=self, exec_res=exec_res, logger=logger)


def _compute_plan_for_attempt(self, **kwargs: Any) -> tuple[PlannerResult, Dict[str, Any], str]:
    return runtime_compute_plan_for_attempt(self, **kwargs)


def _record_planning_attempt(self, **kwargs: Any) -> None:
    orch_record_planning_attempt(self, **kwargs)


def _finalize_goal_result(self, **kwargs: Any) -> CognitiveResult:
    return orch_finalize_goal_result(
        self,
        **kwargs,
        result_factory=CognitiveResult,
        skill_miner_ref=SkillMiner,
    )


def _warmup_task_runtime(self, **kwargs: Any) -> str:
    return orch_warmup_task_runtime(self, **kwargs)


async def _collect_historical_goal_context(self, **kwargs: Any) -> str:
    return await orch_collect_historical_goal_context(self, **kwargs)


def _run_proactive_perception_and_contract(self, **kwargs: Any) -> None:
    orch_run_proactive_perception_and_contract(self, **kwargs)


def _check_cognitive_fingerprint_hit(self, **kwargs: Any) -> tuple[Any, Any, Optional[CognitiveResult]]:
    return orch_check_cognitive_fingerprint_hit(self, **kwargs, result_factory=CognitiveResult)


def _run_semantic_presensing_short_circuit(self, **kwargs: Any) -> Optional[CognitiveResult]:
    return orch_run_semantic_presensing_short_circuit(self, **kwargs, result_factory=CognitiveResult)


def _evaluate_attempt_outcome(self, **kwargs: Any) -> tuple[Any, int, bool]:
    return orch_evaluate_attempt_outcome(self, **kwargs)


def _record_capability_gaps(self, **kwargs: Any) -> None:
    orch_record_capability_gaps(self, **kwargs)


async def _handle_attempt_execution_and_feedback(self, **kwargs: Any) -> Dict[str, Any]:
    return await orch_handle_attempt_execution_and_feedback(self, **kwargs)


async def _prepare_run_context(self, **kwargs: Any) -> PreparedRunContext:
    return await orch_prepare_run_context(self, **kwargs)


async def _run_single_attempt(self, **kwargs: Any) -> str:
    return await orch_run_single_attempt(self, **kwargs)


async def _run_goal_internal(self, task: CognitiveTask) -> CognitiveResult:
    return await goal_flow_run_goal_internal(self, task=task)


def install_loop_shims(loop_cls: type) -> None:
    """Install API-facing thin wrappers onto `CognitiveLoop`."""
    loop_cls._generate_sensing_report = _generate_sensing_report
    loop_cls._get_environment_snapshot = _get_environment_snapshot
    loop_cls._infer_pre_sensing_focus_paths = _infer_pre_sensing_focus_paths
    loop_cls._compact_last_execution_for_planner = staticmethod(ctx_compact_last_execution_for_planner)
    loop_cls._infer_focus_paths_from_last_execution = staticmethod(runtime_infer_focus_paths_from_last_execution)
    loop_cls._get_candidate_files = _get_candidate_files
    loop_cls._summarize_history = _summarize_history
    loop_cls._collect_runtime_perception = _collect_runtime_perception
    loop_cls._refresh_planner_environment_snapshot = _refresh_planner_environment_snapshot
    loop_cls._build_base_planner_context = _build_base_planner_context
    loop_cls._build_effective_planner_context = _build_effective_planner_context
    loop_cls._update_task_from_perception_snapshot = _update_task_from_perception_snapshot
    loop_cls._apply_attention_context = _apply_attention_context
    loop_cls._try_reflex_plan_from_perception = _try_reflex_plan_from_perception
    loop_cls._sanitize_executor_output = _sanitize_executor_output
    loop_cls._compute_plan_for_attempt = _compute_plan_for_attempt
    loop_cls._extract_planner_trace_signals = staticmethod(orch_extract_planner_trace_signals)
    loop_cls._record_planning_attempt = _record_planning_attempt
    loop_cls._apply_feedback_to_runtime_state = staticmethod(orch_apply_feedback_to_runtime_state)
    loop_cls._finalize_goal_result = _finalize_goal_result
    loop_cls._warmup_task_runtime = _warmup_task_runtime
    loop_cls._collect_historical_goal_context = _collect_historical_goal_context
    loop_cls._run_proactive_perception_and_contract = _run_proactive_perception_and_contract
    loop_cls._check_cognitive_fingerprint_hit = _check_cognitive_fingerprint_hit
    loop_cls._run_semantic_presensing_short_circuit = _run_semantic_presensing_short_circuit
    loop_cls._evaluate_attempt_outcome = _evaluate_attempt_outcome
    loop_cls._record_capability_gaps = _record_capability_gaps
    loop_cls._handle_attempt_execution_and_feedback = _handle_attempt_execution_and_feedback
    loop_cls._prepare_run_context = _prepare_run_context
    loop_cls._run_single_attempt = _run_single_attempt
    loop_cls._run_goal_internal = _run_goal_internal


__all__ = ["install_loop_shims"]
