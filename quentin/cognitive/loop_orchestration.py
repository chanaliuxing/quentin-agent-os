from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import logging
import os

from quentin.immune.anomaly import MetricSnapshot
from quentin.traces.core import TraceEventType, new_trace_event
from quentin.utils.time import now_utc
from quentin.goals.done_definition import DoneCheckContext
from quentin.council.manager import CouncilQuestion
from quentin.memory.models import MemoryTier
from quentin.infra.llm.error_classifier import error_classifier
from quentin.cognitive.attempt_evaluator import evaluate_attempt_result
from quentin.cognitive.compaction import compact_session_context
from quentin.agents.pi_embedded_helpers.repetition_detection import detect_repetitive_sequence
from quentin.memory.kinds import KIND_CAPABILITY_GAP
from quentin.cognitive.learning_writeback import write_skill_idea_requests, write_task_lessons_and_gist

logger = logging.getLogger(__name__)


def _emit_loop_event(
    loop: Any,
    *,
    session_id: str,
    goal_id: str,
    event_type: str,
    category: str,
    phase: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    queue = getattr(loop, "system_event_queue", None)
    if queue is None:
        return
    try:
        queue.emit_brain_event(
            session_id=str(session_id or "global"),
            event_type=str(event_type or "turn_update"),
            category=str(category or "system"),
            phase=str(phase or "update"),
            source="cognitive_loop",
            payload=dict(payload or {}),
            turn_id=str(goal_id or ""),
        )
    except Exception:
        pass


def build_sensing_evidence_index(sensing_report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build a robust path->evidence index from heterogeneous sensing report layouts.

    Supports:
    - current layout: {"evidence": [{"path": "...", ...}, ...]}
    - legacy/nested layouts where evidence can appear under nested dictionaries.
    """
    index: Dict[str, Dict[str, Any]] = {}
    if not isinstance(sensing_report, dict):
        return index

    evidence = sensing_report.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path:
                index[path] = item
        if index:
            return index

    # Backward-compatible fallback for nested/legacy shapes.
    stack: List[Any] = [sensing_report]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if isinstance(node.get("path"), str):
                p = str(node.get("path") or "").strip()
                if p and isinstance(node.get("exists"), bool):
                    index[p] = node
            for v in node.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(node, list):
            for v in node:
                if isinstance(v, (dict, list)):
                    stack.append(v)
    return index


@dataclass
class LoopRuntimeState:
    failure_count: int = 0
    consecutive_errors: int = 0
    last_error_msg: str = ""
    final_output: str = ""
    actions_summary: str = ""
    done_result: Any = None
    tool_only_no_update_count: int = 0
    overflow_compacted: bool = False
    current_think_level: str = "off"
    attempted_thinking: set[str] = field(default_factory=set)
    last_plan_result: Optional[Any] = None
    last_exec_result: Dict[str, Any] = field(default_factory=dict)
    recent_traces: List[Dict[str, Any]] = field(default_factory=list)
    recent_snapshots: List[MetricSnapshot] = field(default_factory=list)
    latest_self_awareness: Optional[Any] = None
    call_history: List[str] = field(default_factory=list) # List of tool call fingerprints
    critical_instruction: str = "" # Injected for loop breakout
    last_reset_failure_count: int = 0
    repetition_streak: int = 0
    tool_loop_streak: int = 0
    interrupt_cooldown_remaining: int = 0


@dataclass
class PreparedRunContext:
    session_id: str
    goal: Any
    historical_context: str
    perception_data: Dict[str, Any]
    executor: Any
    idempotency: Any
    early_result: Optional[Any] = None


def extract_planner_trace_signals(plan_raw_output: str) -> tuple[List[str], Dict[str, Any]]:
    planner_repairs: List[str] = []
    discovery_guard: Dict[str, Any] = {}
    try:
        parsed_plan = json.loads(plan_raw_output or "{}")
        repairs = parsed_plan.get("planner_repairs") if isinstance(parsed_plan, dict) else []
        if isinstance(repairs, list):
            planner_repairs = [str(x) for x in repairs[:8]]
        dg = parsed_plan.get("discovery_guard") if isinstance(parsed_plan, dict) else {}
        if isinstance(dg, dict):
            discovery_guard = dict(dg)
    except Exception:
        planner_repairs = []
        discovery_guard = {}
    return planner_repairs, discovery_guard


def record_planning_attempt(
    loop: Any,
    *,
    trace_id: str,
    attempt_index: int,
    goal: Any,
    plan_result: Any,
    env_snapshot: str,
    planner_ctx: Dict[str, Any],
) -> None:
    planner_repairs, discovery_guard = extract_planner_trace_signals(plan_result.raw_output)
    eval_data = planner_ctx.get("last_attempt_evaluation") if isinstance(planner_ctx.get("last_attempt_evaluation"), dict) else {}
    lifecycle = planner_ctx.get("planner_lifecycle_payload") if isinstance(planner_ctx.get("planner_lifecycle_payload"), dict) else {}
    strategy_patch = planner_ctx.get("planning_strategy_patch") if isinstance(planner_ctx.get("planning_strategy_patch"), dict) else {}
    payload_variant = planner_ctx.get("planner_payload_variant") if isinstance(planner_ctx.get("planner_payload_variant"), dict) else {}
    retry_delta = planner_ctx.get("retry_plan_delta") if isinstance(planner_ctx.get("retry_plan_delta"), dict) else {}
    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.PLANNING,
                payload={
                    "attempt_index": attempt_index,
                    "goal_id": goal.goal_id,
                    "steps": plan_result.steps,
                    "raw_output": str(plan_result.raw_output or ""),
                    "used_skills": plan_result.used_skills,
                    "planner_repairs": planner_repairs,
                    "discovery_guard": discovery_guard,
                    "context_injected": {
                        "tree_lines": int(len(str(env_snapshot or "").splitlines())),
                        "candidate_files_count": int(
                            len(planner_ctx.get("candidate_files") or [])
                        ) if isinstance(planner_ctx, dict) else 0,
                        "retry_plan_delta": (planner_ctx.get("retry_plan_delta") or {}) if isinstance(planner_ctx, dict) else {},
                        "skill_suggestions_count": int(len(planner_ctx.get("skill_suggestions") or [])) if isinstance(planner_ctx, dict) else 0,
                        "tool_knowledge_count": int(len(planner_ctx.get("tool_knowledge") or [])) if isinstance(planner_ctx, dict) else 0,
                        "tool_summaries_count": int(len(planner_ctx.get("tool_summaries") or {})) if isinstance(planner_ctx, dict) else 0,
                    "planning_diagnostics": {
                        "attempt_stage": str(lifecycle.get("stage") or ""),
                        "attempt_band": str(lifecycle.get("attempt_band") or ""),
                        "force_progress_sync": bool(lifecycle.get("force_progress_sync", False)),
                        "failure_category": str(eval_data.get("category") or ""),
                        "correction_intensity": str(eval_data.get("correction_intensity") or ""),
                        "severity": str(eval_data.get("severity") or ""),
                        "error_subcategory": str(eval_data.get("error_subcategory") or ""),
                        "strategy_patch_id": str(strategy_patch.get("patch_id") or ""),
                        "strategy_patch_category": str(strategy_patch.get("category") or ""),
                        "payload_variant_id": str(payload_variant.get("variant_id") or ""),
                        "payload_tool_family": str(payload_variant.get("tool_family") or ""),
                            "retry_delta_reason": str(retry_delta.get("reason") or ""),
                        },
                    },
                },
            )
        )
    except Exception:
        pass


def maybe_apply_planning_reset(*, state: LoopRuntimeState) -> bool:
    threshold = max(2, int(os.getenv("QUENTIN_PLANNER_RESET_FAILURE_THRESHOLD", "3") or "3"))
    if int(state.failure_count or 0) < threshold:
        return False
    if int(state.last_reset_failure_count or 0) >= int(state.failure_count or 0):
        return False
    state.last_plan_result = None
    state.critical_instruction = (
        "PLANNING RESET MODE: You have failed repeatedly and are likely anchored to a bad decomposition. "
        "Forget previous plan steps and restart from Goal intent + current environment evidence only. "
        "Produce a fresh decomposition and explicitly avoid prior failed path."
    )
    state.last_reset_failure_count = int(state.failure_count or 0)
    return True


def _interrupt_enabled() -> bool:
    raw = str(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_ENABLED", "1") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _derive_attempt_interrupt_state(
    *,
    repetition_streak: int,
    tool_loop_streak: int,
) -> str:
    if not _interrupt_enabled():
        return "none"
    repeat_threshold = max(2, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_REPEAT_THRESHOLD", "2") or "2"))
    tool_loop_threshold = max(2, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_TOOL_LOOP_THRESHOLD", "3") or "3"))
    trigger = max(int(repetition_streak or 0) - repeat_threshold + 1, int(tool_loop_streak or 0) - tool_loop_threshold + 1)
    if trigger >= 2:
        return "hard_reset"
    if trigger >= 1:
        return "interrupt"
    if int(repetition_streak or 0) == repeat_threshold - 1 or int(tool_loop_streak or 0) == tool_loop_threshold - 1:
        return "warn"
    return "none"


def _interrupt_cooldown_length(state: str) -> int:
    key = str(state or "").strip().lower()
    if key == "hard_reset":
        return max(1, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_HARD_RESET_COOLDOWN", "2") or "2"))
    if key == "interrupt":
        return max(1, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN", "1") or "1"))
    return 0


def _infer_interrupt_error_context(*, exec_res: Dict[str, Any]) -> tuple[str, str]:
    subcategory = ""
    origin = "none"
    try:
        from quentin.cognitive.tool_error_subtypes import classify_tool_error_subtype

        _, sub = classify_tool_error_subtype(last_exec_result=exec_res if isinstance(exec_res, dict) else {})
        subcategory = str(sub or "").strip().lower()
    except Exception:
        subcategory = ""

    text_parts: List[str] = []
    if isinstance(exec_res, dict):
        raw = exec_res.get("raw") if isinstance(exec_res.get("raw"), dict) else {}
        text_parts.append(str(exec_res.get("error") or ""))
        text_parts.append(str(raw.get("error") or ""))
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        for s in steps[-8:]:
            if not isinstance(s, dict):
                continue
            text_parts.append(str(s.get("error") or ""))
            res = s.get("result") if isinstance(s.get("result"), dict) else {}
            text_parts.append(str(res.get("error") or ""))
            tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
            text_parts.append(str(tr.get("error") or ""))
    text = " | ".join(text_parts).lower()
    model_markers = ("syntaxerror", "jsondecodeerror", "invalid json", "parse", "format", "unexpected token")
    env_markers = ("timeout", "timed out", "permission denied", "not found", "connection", "rate limit", "resource busy")
    has_model = any(m in text for m in model_markers)
    has_env = any(m in text for m in env_markers)
    if has_model and has_env:
        origin = "mixed"
    elif has_env:
        origin = "environment"
    elif has_model:
        origin = "model"
    return subcategory, origin


def _adaptive_interrupt_cooldown_length(
    *,
    state: str,
    error_subcategory: str,
    error_origin: str,
    repetition_streak: int,
    tool_loop_streak: int,
) -> int:
    base = _interrupt_cooldown_length(state)
    sub = str(error_subcategory or "").strip().lower()
    origin = str(error_origin or "").strip().lower()
    bonus = 0
    if any(k in sub for k in ("timeout", "permission_denied", "navigation_timeout")):
        bonus += 1
    if origin in {"environment", "mixed"}:
        bonus += 1
    if max(int(repetition_streak or 0), int(tool_loop_streak or 0)) >= 4:
        bonus += 1
    if str(state or "").strip().lower() == "hard_reset":
        bonus += 1

    if str(state or "").strip().lower() == "hard_reset":
        max_len = max(2, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_HARD_RESET_COOLDOWN_MAX", "4") or "4"))
    else:
        max_len = max(1, int(os.getenv("QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN_MAX", "3") or "3"))
    return max(0, min(max_len, base + bonus))


def apply_feedback_to_runtime_state(
    *,
    state: LoopRuntimeState,
    feedback: Dict[str, Any],
) -> tuple[bool, bool]:
    state.current_think_level = str(feedback.get("current_think_level") or state.current_think_level)
    state.overflow_compacted = bool(feedback.get("overflow_compacted", state.overflow_compacted))
    state.consecutive_errors = int(feedback.get("consecutive_errors", state.consecutive_errors))
    state.last_error_msg = str(feedback.get("last_error_msg", state.last_error_msg))
    state.failure_count = int(feedback.get("failure_count", state.failure_count))
    state.tool_only_no_update_count = int(
        feedback.get("tool_only_no_update_count", state.tool_only_no_update_count)
    )
    state.latest_self_awareness = feedback.get("latest_self_awareness") or state.latest_self_awareness
    if feedback.get("final_output") is not None:
        state.final_output = str(feedback.get("final_output") or "")
    if feedback.get("actions_summary") is not None:
        state.actions_summary = str(feedback.get("actions_summary") or "")
    if feedback.get("done_result") is not None:
        state.done_result = feedback.get("done_result")
    return bool(feedback.get("retry_same_attempt")), bool(feedback.get("should_break"))


def warmup_task_runtime(loop: Any, *, task: Any, trace_id: str) -> str:
    from quentin.infra.sessions.checkpoint import checkpoint_manager
    from quentin.infra.concurrency.cancellation import default_cancellation_registry

    _ = checkpoint_manager.load_checkpoint(task.task_id)
    cancel_token = default_cancellation_registry().get_or_create(trace_id)
    task.metadata["cancel_token"] = cancel_token

    session_id = getattr(task, "session_id", None) or "global"
    loop.memory_fabric.warm_session(session_id)
    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.TASK_RECEIVED,
                payload={"task": task.to_dict()},
            )
        )
    except Exception:
        pass
    return str(session_id)


async def collect_historical_goal_context(loop: Any, *, goal: Any) -> str:
    historical_context = ""
    try:
        from quentin.memory.models import MemoryQuery

        prev_memories = loop.memory_fabric.recall(MemoryQuery(text=f"goal:{goal.goal_id}", top_k=5))
        if prev_memories:
            historical_context = await loop._summarize_history(prev_memories, goal.goal_id)
            logger.info(f"CognitiveLoop: Recalled and summarized history for goal {goal.goal_id}")
    except Exception as e:
        logger.debug(f"CognitiveLoop: Failed to recall history: {e}")
    return historical_context


def run_proactive_perception_and_contract(loop: Any, *, task: Any) -> None:
    print(f"👀 [Perception] Proactively scanning environment and attachments...")
    perception_ctx = {
        "task_input": task.input_text,
        "focus_paths": loop._infer_pre_sensing_focus_paths(task),
        "attachments": task.metadata.get("attachments", []),
        "domain": task.domain,
        "environment": task.environment,
    }
    if loop.perception_layer:
        try:
            proactive_snapshot = loop.perception_layer.build_snapshot(ctx=perception_ctx)
            task.metadata["proactive_perception"] = proactive_snapshot.metadata
            logger.info(f"CognitiveLoop: Proactive perception completed. Items: {list(proactive_snapshot.metadata.keys())}")
        except Exception as e:
            logger.warning(f"CognitiveLoop: Proactive perception failed: {e}")

    contract = loop.contractor.build_contract(
        task_input=task.input_text,
        task_id=task.task_id,
        perception_data=task.metadata.get("proactive_perception", {}),
        metadata=task.metadata,
    )
    task.metadata["cognitive_contract"] = contract
    print(f"📝 [Contract] Requirement atomized: {contract.intent} ({contract.domain})")


def check_cognitive_fingerprint_hit(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    env_snapshot: str,
    result_factory: Any,
) -> tuple[Any, Any, Optional[Any]]:
    executor = getattr(loop, "executor", None)
    idempotency = getattr(executor, "idempotency_gate", None) if executor else None
    if not idempotency:
        return executor, idempotency, None
    target_domain = getattr(goal, "domain", "core")
    tm = getattr(executor, "tool_manager", None)
    tools = tm.get_tool_names_by_domain(str(target_domain)) if tm else []

    cog_fingerprint = idempotency.get_cognitive_fingerprint(
        task_input=task.input_text,
        env_summary=env_snapshot,
        tools=tools,
    )
    cog_hit = idempotency.check_detail(cog_fingerprint)
    if not cog_hit.get("hit"):
        return executor, idempotency, None
    print(f"🎯 [Fingerprint] HIT! Reusing successful result from cognitive cache.")
    logger.info(f"CognitiveLoop: Cognitive fingerprint HIT for task {task.task_id}")
    from quentin.goals.done_definition import DoneCheckResult
    result = result_factory(
        task_id=task.task_id,
        goal_id=goal.goal_id,
        final_output=cog_hit.get("final_output", ""),
        plan_summary="[Cognitive Hit] Reused past plan.",
        actions_summary="[Cognitive Hit] State matched previous success.",
        done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=["Cognitive fingerprint match"]),
        done=True,
        done_confidence=1.0,
        self_awareness={"cognitive_hit": True},
    )
    return executor, idempotency, result


def run_semantic_presensing_short_circuit(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    trace_id: str,
    result_factory: Any,
) -> Optional[Any]:
    if os.getenv("QUENTIN_ENABLE_PRE_SENSING", "1") != "1" or loop._planner is not None:
        return None
    try:
        focus_paths = loop._infer_pre_sensing_focus_paths(task)
        sensing_report = loop._generate_sensing_report(task, focus_paths)
        print(f"\n🔍 [Pre-sensing] Focused Sensing Active. Paths: {focus_paths}\n")
        pre_sensing_prompt = (
            "Requirement Context (Desired State):\n"
            f"{task.input_text}\n\n"
            "Actual Sensing Report (Real-world Environment Evidence):\n"
            f"{json.dumps(sensing_report, indent=2)}\n\n"
            "MISSION: Assess if the requirement is ALREADY fully satisfied based ONLY on evidence in the Sensing Report.\n"
            "CRITICAL REASONING PROTOCOL:\n"
            "1. ABSENCE != COMPLETION: If a file or directory required by the goal is NOT listed in the Sensing Report, the verdict MUST be 'not_done'.\n"
            "2. EVIDENCE-BASED ONLY: To give an 'already_done' verdict, you MUST find explicit evidence (e.g., 'exists': true AND 'functional_check': 'pass') for EVERY core component of the task.\n"
            "3. COMPARE EXPECTED VS ACTUAL: Look at 'focus_paths' in the report. If any path has 'exists': false, the task is NOT done.\n"
            "4. IGNORE WISHFUL THINKING: Do NOT assume a task is done just because it is described in the 'Requirement Context'. Use the 'Actual Sensing Report' as the ONLY source of truth.\n"
            "5. CONFIDENCE GUARD: If there is any ambiguity or missing evidence for a critical file, confidence MUST be < 0.5.\n"
            "\n"
            "Your response must be a JSON object with:\n"
            "1. 'verdict': 'already_done' | 'not_done'\n"
            "2. 'evidence_summary': detailed explanation citing specific evidence or missing items\n"
            "3. 'confidence': 0.0 to 1.0\n"
            "Return JSON ONLY."
        )
        pre_sensing_q = CouncilQuestion(
            topic="pre_sensing",
            importance="low",
            prompt=pre_sensing_prompt,
            payload={"goal_id": goal.goal_id},
        )
        print(f"👀 [Pre-sensing] Scanning environment for existing clues...")
        pre_sensing_res = loop.council_manager.run_council("pre_sensing", pre_sensing_q)
        verdict = pre_sensing_res.final.get("verdict")

        # P0: Physical Guard - If focus paths explicitly don't exist, override verdict
        sensing_hallucination_blocked = False
        evidence_map = build_sensing_evidence_index(sensing_report)
        for path in (focus_paths or []):
            stat = evidence_map.get(path)
            if isinstance(stat, dict) and stat.get("exists") is False:
                if verdict == "already_done":
                    sensing_hallucination_blocked = True
                verdict = "not_done"
                break

        if verdict != "already_done":
            if sensing_hallucination_blocked:
                print(f"🛑 [Pre-sensing] Hallucination BLOCKED! Brain claimed 'done', but physical evidence shows {path} is MISSING.")
                try:
                    loop.trace_recorder.record_event(
                        new_trace_event(
                            trace_id=trace_id,
                            event_type=TraceEventType.DECISION,
                            payload={
                                "action": "pre_sensing_hallucination_blocked",
                                "goal_id": goal.goal_id,
                                "missing_path": path,
                            },
                        )
                    )
                except Exception:
                    pass
            return None
        conf = float(pre_sensing_res.final.get("confidence", 0.0))
        if conf < 0.8:
            return None
        print(f"✅ [Pre-sensing] HIT! Brain realized this task is ALREADY complete (confidence={conf*100:.1f}%).")
        print(f"   Evidence: {pre_sensing_res.final.get('evidence_summary', 'Matched existing state')}")
        logger.info(f"CognitiveLoop: Semantic Pre-sensing HIT. Goal {goal.goal_id} already satisfied (conf={conf}).")
        from quentin.goals.done_definition import DoneCheckResult
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "pre_sensing_short_circuit",
                        "goal_id": goal.goal_id,
                        "verdict": verdict,
                        "confidence": conf,
                        "evidence_summary": pre_sensing_res.final.get("evidence_summary"),
                        "focus_paths": focus_paths,
                    },
                )
            )
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.SUMMARY,
                    payload={
                        "task_id": task.task_id,
                        "goal_id": goal.goal_id,
                        "done": True,
                        "final_output_preview": "already_done (pre_sensing)",
                        "metrics": {
                            "total_attempts": 0,
                            "success_attempts": 0,
                            "error_attempts": 0,
                            "latency_ms": 0.0,
                            "tool_call_count": 0,
                        },
                    },
                )
            )
        except Exception:
            pass
        return result_factory(
            task_id=task.task_id,
            goal_id=goal.goal_id,
            final_output=f"Goal already satisfied (verified by pre-sensing). Evidence: {pre_sensing_res.final.get('evidence_summary')}",
            plan_summary="Skipped: already done.",
            actions_summary="Semantic match found.",
            done_result=DoneCheckResult(is_done=True, confidence=conf, reasons=[f"Pre-sensing match: {pre_sensing_res.final.get('evidence_summary')}"]),
            done=True,
            done_confidence=conf,
            self_awareness={"idempotent_hit": True, "pre_sensing_verdict": verdict},
        )
    except Exception as e:
        logger.debug(f"Pre-sensing failed: {e}")
        return None


def finalize_goal_result(
    loop: Any,
    *,
    start_ts: str,
    trace_id: str,
    task: Any,
    goal: Any,
    last_plan_result: Optional[Any],
    actions_summary: str,
    final_output: str,
    done_result: Optional[Any],
    metrics: Dict[str, Any],
    last_exec_result: Dict[str, Any],
    latest_self_awareness: Optional[Any],
    idempotency: Any,
    executor: Any,
    result_factory: Any,
    skill_miner_ref: Any,
) -> Any:
    loop._write_trace(
        trace_id=trace_id,
        task=task,
        goal=goal,
        plan_summary=last_plan_result.raw_output if last_plan_result else "",
        actions_summary=actions_summary,
        final_output=final_output,
        done_result=done_result,
        start_ts=start_ts,
        metrics=metrics,
    )
    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.SUMMARY,
                payload={
                    "task_id": task.task_id,
                    "goal_id": goal.goal_id,
                    "done": bool(done_result.is_done) if done_result else False,
                    "final_output_preview": (final_output or "")[:2000],
                    "metrics": metrics,
                },
            )
        )
    except Exception:
        pass

    loop._write_memory(
        task=task,
        goal=goal,
        plan_summary=last_plan_result.raw_output if last_plan_result else "",
        actions_summary=actions_summary,
        final_output=final_output,
        done_result=done_result,
    )
    try:
        session_id = (
            (task.metadata or {}).get("session_id")
            if isinstance(getattr(task, "metadata", None), dict)
            else None
        ) or getattr(task, "task_id", "")
        write_task_lessons_and_gist(
            loop,
            session_id=str(session_id),
            trace_id=str(trace_id),
            task=task,
            goal=goal,
            plan_summary=last_plan_result.raw_output if last_plan_result else "",
            actions_summary=actions_summary,
            final_output=final_output,
            done_result=done_result,
            last_exec_result=last_exec_result if isinstance(last_exec_result, dict) else {},
        )
    except Exception:
        pass
    result = result_factory(
        task_id=task.task_id,
        goal_id=goal.goal_id,
        final_output=final_output,
        plan_summary=last_plan_result.raw_output if last_plan_result else "",
        actions_summary=actions_summary,
        done_result=done_result,
        done=done_result.is_done if done_result else False,
        done_confidence=done_result.confidence if done_result else 0.0,
        raw_executor_result=last_exec_result.get("raw"),
        self_awareness=(latest_self_awareness.to_dict() if latest_self_awareness else {}),
    )
    if result.done and idempotency:
        try:
            target_domain = getattr(goal, "domain", "core")
            tm = getattr(executor, "tool_manager", None)
            tools = tm.get_tool_names_by_domain(str(target_domain)) if tm else []
            env_summary = loop._get_environment_snapshot(task=task)
            final_cog_fingerprint = idempotency.get_cognitive_fingerprint(
                task_input=task.input_text,
                env_summary=env_summary,
                tools=tools,
            )
            idempotency.mark_success(
                fingerprint=final_cog_fingerprint,
                plan_fragment={"steps": last_plan_result.steps} if last_plan_result else None,
                final_output=final_output,
            )
            logger.info(f"CognitiveLoop: Recorded cognitive success for task {task.task_id}")
        except Exception as e:
            logger.warning(f"CognitiveLoop: Failed to record cognitive fingerprint: {e}")
    if result.done:
        from quentin.infra.sessions.checkpoint import checkpoint_manager
        checkpoint_manager.clear_checkpoint(task.task_id)
        if (os.getenv("QUENTIN_ENABLE_SKILL_MINING", "1") == "1" and str(task.domain) != "maintenance"):
            try:
                miner_cls = skill_miner_ref
                if miner_cls is None:
                    from quentin.skills.miner import SkillMiner as miner_cls  # type: ignore[no-redef]
                miner = miner_cls(registry=loop.skill_manager.registry)
                events = loop.trace_recorder.get_events(trace_id) if hasattr(loop.trace_recorder, "get_events") else []
                cand = miner.mine_from_task(task=task, result=result, trace_events=events)
                if cand:
                    logger.info(f"Skill Evolution: Mined new skill candidate '{cand.name}' from task {task.task_id}")
                    loop.trace_recorder.record_event(
                        new_trace_event(
                            trace_id=trace_id,
                            event_type=TraceEventType.SKILL_EVOLUTION,
                            payload={"action": "skill_mined", "candidate_id": cand.candidate_id, "name": cand.name},
                        )
                    )
            except Exception as e:
                logger.debug(f"Skill mining failed: {e}")
    return result


async def prepare_run_context(loop: Any, *, task: Any, trace_id: str) -> PreparedRunContext:
    perception_data = await loop._collect_runtime_perception(task)
    session_id = loop._warmup_task_runtime(task=task, trace_id=trace_id)
    goal = loop._ensure_goal(task)

    print(f"\n{'='*60}")
    print(f"🧠 [Cognitive Loop] Task Initiation")
    print(f"   Target Goal: {goal.title[:100]}...")
    print(f"   Goal ID:     {goal.goal_id}")
    print(f"   Trace ID:    {trace_id}")
    print(f"{'='*60}\n")

    historical_context = await loop._collect_historical_goal_context(goal=goal)
    loop._run_proactive_perception_and_contract(task=task)
    env_snapshot = loop._get_environment_snapshot(task=task)
    executor, idempotency, hit_result = loop._check_cognitive_fingerprint_hit(
        task=task,
        goal=goal,
        env_snapshot=env_snapshot,
    )
    if hit_result is not None:
        return PreparedRunContext(
            session_id=session_id,
            goal=goal,
            historical_context=historical_context,
            perception_data=perception_data,
            executor=executor,
            idempotency=idempotency,
            early_result=hit_result,
        )
    pre_sensing_result = loop._run_semantic_presensing_short_circuit(
        task=task,
        goal=goal,
        trace_id=trace_id,
    )
    if pre_sensing_result is not None:
        return PreparedRunContext(
            session_id=session_id,
            goal=goal,
            historical_context=historical_context,
            perception_data=perception_data,
            executor=executor,
            idempotency=idempotency,
            early_result=pre_sensing_result,
        )
    return PreparedRunContext(
        session_id=session_id,
        goal=goal,
        historical_context=historical_context,
        perception_data=perception_data,
        executor=executor,
        idempotency=idempotency,
        early_result=None,
    )


async def run_single_attempt(
    loop: Any,
    *,
    task: Any,
    run_ctx: PreparedRunContext,
    trace_id: str,
    loop_idx: int,
    metrics: Dict[str, Any],
    state: LoopRuntimeState,
    self_awareness_engine: Any,
) -> str:
    attempt_started_at = now_utc()
    loop._run_checkpoint(task.task_id, loop_idx, metrics)
    await loop._check_context_and_flush(run_ctx.goal, metrics, run_ctx.session_id)
    if maybe_apply_planning_reset(state=state):
        logger.warning(
            "CognitiveLoop: planning reset applied at failure_count=%s",
            state.failure_count,
        )
    if int(state.interrupt_cooldown_remaining or 0) > 0:
        cooldown_instruction = (
            "INTERRUPT COOLDOWN ACTIVE: this attempt must begin with bounded diagnostics and progress sync. "
            "Avoid mutating actions until diagnostics succeed."
        )
        if state.critical_instruction:
            state.critical_instruction = (state.critical_instruction + "\n" + cooldown_instruction).strip()
        else:
            state.critical_instruction = cooldown_instruction

    plan_result, planner_ctx, env_snapshot = loop._compute_plan_for_attempt(
        task=task,
        goal=run_ctx.goal,
        session_id=run_ctx.session_id,
        trace_id=trace_id,
        attempt_index=metrics["total_attempts"],
        historical_context=run_ctx.historical_context,
        last_plan_result=state.last_plan_result,
        last_exec_result=state.last_exec_result,
        latest_self_awareness=state.latest_self_awareness,
        perception_data=run_ctx.perception_data,
        critical_instruction=state.critical_instruction,
        failure_count=state.failure_count,
        tool_only_no_update_count=state.tool_only_no_update_count,
        retry_budget_remaining=float(metrics.get("retry_budget_remaining", 0.0) or 0.0),
        interrupt_cooldown_remaining=int(state.interrupt_cooldown_remaining or 0),
    )
    if state.critical_instruction:
        logger.info("CognitiveLoop: Consumed critical instruction for breakout.")
        state.critical_instruction = ""
    if int(state.interrupt_cooldown_remaining or 0) > 0:
        state.interrupt_cooldown_remaining = max(0, int(state.interrupt_cooldown_remaining or 0) - 1)
    state.last_plan_result = plan_result
    print(f"\n🎬 [Script] Brain formulated a {len(plan_result.steps)}-step plan:")
    for s in plan_result.steps:
        print(f"   [{s.get('step_id')}] {s.get('description')}")
    print("")
    plan_summary = plan_result.raw_output
    record_planning_attempt(
        loop,
        trace_id=trace_id,
        attempt_index=metrics["total_attempts"],
        goal=run_ctx.goal,
        plan_result=plan_result,
        env_snapshot=env_snapshot,
        planner_ctx=planner_ctx,
    )

    print(f"🚀 [Execution] Attempt #{loop_idx} started...")
    progressive_pressure = state.tool_only_no_update_count >= 3
    task.metadata["think_level"] = state.current_think_level
    state.attempted_thinking.add(state.current_think_level)

    exec_res = await loop._run_executor_or_custom(
        task,
        run_ctx.goal,
        plan_result.raw_output,
        progressive_pressure=progressive_pressure,
        self_awareness=state.latest_self_awareness,
    )
    state.last_exec_result = exec_res
    feedback = await loop._handle_attempt_execution_and_feedback(
        task=task,
        goal=run_ctx.goal,
        trace_id=trace_id,
        session_id=run_ctx.session_id,
        loop_idx=loop_idx,
        plan_result=plan_result,
        plan_summary=plan_summary,
        exec_res=exec_res,
        attempt_started_at=attempt_started_at,
        metrics=metrics,
        state=state,
        recent_traces=state.recent_traces,
        recent_snapshots=state.recent_snapshots,
        latest_self_awareness=state.latest_self_awareness,
        self_awareness_engine=self_awareness_engine,
        failure_count=state.failure_count,
        tool_only_no_update_count=state.tool_only_no_update_count,
        consecutive_errors=state.consecutive_errors,
        last_error_msg=state.last_error_msg,
        current_think_level=state.current_think_level,
        attempted_thinking=state.attempted_thinking,
        overflow_compacted=state.overflow_compacted,
    )
    retry_same_attempt, should_break = apply_feedback_to_runtime_state(
        state=state,
        feedback=feedback,
    )
    if retry_same_attempt:
        return "retry"
    if should_break:
        return "break"
    return "continue"


def evaluate_attempt_outcome(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    trace_id: str,
    loop_idx: int,
    metrics: Dict[str, Any],
    plan_result: Any,
    plan_summary: str,
    exec_res: Dict[str, Any],
    final_output: str,
    actions_summary: str,
    snapshot: MetricSnapshot,
    recent_snapshots: List[MetricSnapshot],
    recent_traces: List[Dict[str, Any]],
    latest_self_awareness: Any,
    failure_count: int,
) -> tuple[Any, int, bool]:
    execution_summary = {
        "plan_steps": plan_result.steps,
        "executor_result": exec_res,
        "attempt_index": metrics["total_attempts"],
        "failure_count": failure_count,
        "final_output": final_output,
        "actions_summary": actions_summary,
        "attempt_evaluation": metrics.get("last_attempt_evaluation", {}),
    }

    # P2: Inject real audit evidence to prevent reflection hallucinations
    audit_logs = ""
    try:
        audit_path = loop.repo_root / "data" / "audit_events.jsonl"
        if audit_path.exists():
            lines = audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Get last 5 relevant events for this trace/goal
            recent_audit = [line for line in lines[-100:] if trace_id in line or goal.goal_id in line][-5:]
            audit_logs = "\n".join(recent_audit)
    except Exception:
        pass

    done_ctx = DoneCheckContext(
        task_id=task.task_id,
        plan_summary=plan_summary,
        actions_summary=actions_summary,
        final_output=final_output,
        metrics={
            **metrics,
            "self_awareness_status": latest_self_awareness.status,
            "self_awareness_failure_rate": latest_self_awareness.failure_rate,
            "self_awareness_failover_reason": latest_self_awareness.failover_reason or "",
            "self_awareness_consecutive_system_errors": latest_self_awareness.consecutive_system_errors,
        },
        logs_excerpt=audit_logs, # Injected audit logs here
    )

    is_system_error = exec_res.get("is_system_error", False)
    raw_exec = exec_res.get("raw")
    exec_failed = bool(isinstance(raw_exec, dict) and raw_exec.get("success") is False)
    if is_system_error:
        logger.warning(f"CognitiveLoop: System error detected in attempt {loop_idx}. Skipping council.")
        from quentin.goals.done_definition import DoneCheckResult
        done_result = DoneCheckResult(is_done=False, confidence=0.0, reasons=[f"System Error: {actions_summary}"])
    elif exec_failed:
        from quentin.goals.done_definition import DoneCheckResult
        reason = "Executor failed"
        try:
            steps = raw_exec.get("steps") if isinstance(raw_exec, dict) else None
            if isinstance(steps, list) and steps:
                last = steps[-1] if isinstance(steps[-1], dict) else {}
                last_res = last.get("result") if isinstance(last, dict) else None
                if isinstance(last_res, dict):
                    reason = str(last_res.get("error") or last_res.get("status") or reason)
                elif last_res:
                    reason = str(last_res)
        except Exception:
            pass
        done_result = DoneCheckResult(is_done=False, confidence=0.0, reasons=[reason])
    else:
        done_result = loop.goal_manager.check_done_and_record(goal=goal, context=done_ctx)

    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.CRITIC,
                payload={
                    "attempt_index": metrics["total_attempts"],
                    "goal_id": goal.goal_id,
                    "self_awareness_status": latest_self_awareness.status,
                    "self_awareness_failure_rate": latest_self_awareness.failure_rate,
                    "self_awareness_failover_reason": latest_self_awareness.failover_reason,
                    "done": bool(done_result.is_done),
                    "confidence": float(done_result.confidence),
                    "reasons": list(done_result.reasons or [])[:32],
                    "violated_constraints": list(done_result.violated_constraints or [])[:32],
                },
            )
        )
    except Exception:
        pass

    print(f"\n⚖️ [Judgment] DoneCouncil is reviewing the evidence...")
    print(f"   Verdict:    {'DONE' if done_result.is_done else 'NOT_DONE'}")
    print(f"   Confidence: {done_result.confidence * 100:.1f}%")
    if done_result.reasons:
        print(f"   Reasoning:  {done_result.reasons[0][:200]}...")

    if done_result.is_done:
        print(f"\n🎉 [Success] Brain has fulfilled the mission objective.")
        try:
            md = task.metadata if isinstance(task.metadata, dict) else {}
            budget = md.get("vision_budget") if isinstance(md.get("vision_budget"), dict) else {}
            if budget:
                from quentin.cognitive.vision_budget import record_vision_budget_feedback

                signal = 1.0
                record_vision_budget_feedback(
                    domain=str(task.domain or ""),
                    task_class=str(md.get("vision_task_class") or md.get("task_class") or budget.get("task_class") or "general"),
                    budget=budget,
                    outcome_score=signal,
                    success=True,
                    metadata={
                        "goal_id": str(goal.goal_id or ""),
                        "attempt_index": int(metrics.get("total_attempts") or 0),
                        "done_confidence": float(done_result.confidence or 0.0),
                        "judge_signals": {
                            "done_confidence": float(done_result.confidence or 0.0),
                            "success": True,
                        },
                    },
                )
        except Exception:
            pass
        return done_result, failure_count, True

    immune_action = loop.immune_loop.after_attempt(
        goal=goal,
        metrics=metrics,
        snapshot=snapshot,
        recent_snapshots=recent_snapshots,
        recent_traces=recent_traces,
    )
    if immune_action is not None:
        loop._apply_immune_action(immune_action, goal)

    try:
        from quentin.bootstrap.container import Container
        enabled = (os.getenv("QUENTIN_AUTO_FIXER_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")
        if enabled:
            forbidden = list((task.metadata or {}).get("forbidden_actions") or []) if isinstance(task.metadata, dict) else []
            Container().auto_fixer.on_system_event(
                event_type="error",
                payload={
                    "error": str(done_result.reasons),
                    "goal_id": goal.goal_id,
                    "trace_id": trace_id,
                    "forbidden_actions": forbidden,
                    "gap_reason": getattr(latest_self_awareness, "anti_pattern_reason", "") or "",
                },
            )
            if forbidden:
                Container().auto_fixer.on_system_event(
                    event_type="blocked_actions",
                    payload={"forbidden_actions": forbidden, "goal_id": goal.goal_id, "trace_id": trace_id},
                )
            if getattr(latest_self_awareness, "anti_pattern_reason", None):
                Container().auto_fixer.on_system_event(
                    event_type="capability_gap",
                    payload={"gap_reason": latest_self_awareness.anti_pattern_reason, "goal_id": goal.goal_id, "trace_id": trace_id},
                )
    except Exception:
        pass

    if loop._should_trigger_reflection(goal, metrics, failure_count):
        attempt_evaluation = metrics.get("last_attempt_evaluation")
        if not isinstance(attempt_evaluation, dict):
            attempt_evaluation = {}
        advice = loop.reflection_council.reflect(
            goal=goal,
            last_plan={"steps": plan_result.steps, "raw": plan_result.raw_output},
            last_exec_result=exec_res,
            metrics=metrics,
            failure_count=failure_count,
            attempt_evaluation=attempt_evaluation,
            importance="high",
            recent_traces=recent_traces,
        )
        loop._record_reflection(goal, execution_summary, advice)
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.CRITIC,
                    payload={
                        "attempt_index": metrics["total_attempts"],
                        "goal_id": goal.goal_id,
                        "reflection_action": advice.action,
                        "summary": (advice.summary or "")[:2000],
                    },
                )
            )
        except Exception:
            pass
        if advice.action == "abort":
            logger.warning("CognitiveLoop: Aborting goal based on reflection.")
            return done_result, failure_count, True
        if advice.action == "adjust_goal" and advice.goal_adjustment:
            md = goal.metadata or {}
            md["adjustment_suggestion"] = advice.goal_adjustment
            goal.metadata = md
        if advice.action in ("retry", "adjust_goal", "request_skill"):
            if advice.new_plan:
                loop._cache_plan_override(goal, advice.new_plan)
            if advice.skill_ideas:
                loop._enqueue_skill_ideas_from_reflection(goal, advice.skill_ideas)
                try:
                    session_id = str(session_id or "")
                    write_skill_idea_requests(
                        loop,
                        session_id=session_id,
                        trace_id=str(trace_id),
                        goal_id=str(getattr(goal, "goal_id", "") or ""),
                        domain=str(getattr(task, "domain", "") or "core"),
                        environment=str(getattr(task, "environment", "") or "sandbox"),
                        ideas=[i for i in (advice.skill_ideas or []) if isinstance(i, dict)],
                    )
                except Exception:
                    pass

    # Record non-done attempt feedback for vision budget adaptation.
    try:
        md = task.metadata if isinstance(task.metadata, dict) else {}
        budget = md.get("vision_budget") if isinstance(md.get("vision_budget"), dict) else {}
        if budget:
            from quentin.cognitive.vision_budget import record_vision_budget_feedback

            score = 0.25
            if final_output:
                score = 0.45
            if not is_system_error and exec_failed:
                score = min(score, 0.30)
            sa_failure_rate = 0.0
            try:
                sa_failure_rate = float(getattr(latest_self_awareness, "failure_rate", 0.0) or 0.0)
            except Exception:
                sa_failure_rate = 0.0
            record_vision_budget_feedback(
                domain=str(task.domain or ""),
                task_class=str(md.get("vision_task_class") or md.get("task_class") or budget.get("task_class") or "general"),
                budget=budget,
                outcome_score=float(score),
                success=False,
                metadata={
                    "goal_id": str(goal.goal_id or ""),
                    "attempt_index": int(metrics.get("total_attempts") or 0),
                    "exec_failed": bool(exec_failed),
                    "is_system_error": bool(is_system_error),
                    "done_confidence": float(done_result.confidence or 0.0),
                    "judge_signals": {
                        "done_confidence": float(done_result.confidence or 0.0),
                        "self_awareness_failure_rate": sa_failure_rate,
                        "exec_failed": bool(exec_failed),
                        "is_system_error": bool(is_system_error),
                    },
                },
            )
    except Exception:
        pass

    return done_result, failure_count, False


def record_capability_gaps(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    trace_id: str,
    session_id: str,
    metrics: Dict[str, Any],
    step_records: List[Dict[str, Any]],
) -> None:
    try:
        from quentin.meta.dual_track_router import RuleBasedDualTrackRouter
        from quentin.meta.gap_extractor import extract_capability_gaps_from_exec_steps

        gaps = extract_capability_gaps_from_exec_steps(
            step_records=step_records if isinstance(step_records, list) else [],
            domain=str(task.domain or "core"),
            environment=str(task.environment or "sandbox"),
            trace_id=str(trace_id),
        )
        if not gaps:
            return
        router = RuleBasedDualTrackRouter(repo_root=str(loop.repo_root))
        for gap in gaps[:5]:
            decision = router.route(gap=gap, ctx={"repo_root": str(loop.repo_root)})
            loop.memory_fabric.remember_atomic(
                content=f"CAPABILITY_GAP: {gap.gap_text}\nroute={decision.track} reason={decision.reason}",
                source=f"cognitive_loop:capability_gap:{task.task_id}",
                tier=MemoryTier.STS,
                domain=str(task.domain or "core"),
                importance=0.5,
                tags=["capability_gap", str(task.domain or "core"), str(task.environment or "sandbox")],
                metadata={**gap.to_dict(), "dual_track_decision": decision.to_dict()},
                kind=KIND_CAPABILITY_GAP,
            )
            try:
                loop.system_event_queue.enqueue_event(
                    session_id=session_id,
                    event_type="capability_gap",
                    payload={"gap": gap.to_dict(), "decision": decision.to_dict(), "goal_id": goal.goal_id},
                    source="cognitive_loop",
                )
            except Exception:
                pass
            try:
                loop.trace_recorder.record_event(
                    new_trace_event(
                        trace_id=trace_id,
                        event_type=TraceEventType.DECISION,
                        payload={
                            "action": "capability_gap_detected",
                            "attempt_index": metrics["total_attempts"],
                            "goal_id": goal.goal_id,
                            "gap": gap.to_dict(),
                            "decision": decision.to_dict(),
                        },
                    )
                )
            except Exception:
                pass
    except Exception:
        pass


async def handle_attempt_execution_and_feedback(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    trace_id: str,
    session_id: str,
    loop_idx: int,
    plan_result: Any,
    plan_summary: str,
    exec_res: Dict[str, Any],
    attempt_started_at: Any,
    metrics: Dict[str, Any],
    state: LoopRuntimeState,
    recent_traces: List[Dict[str, Any]],
    recent_snapshots: List[MetricSnapshot],
    latest_self_awareness: Any,
    self_awareness_engine: Any,
    failure_count: int,
    tool_only_no_update_count: int,
    consecutive_errors: int,
    last_error_msg: str,
    current_think_level: str,
    attempted_thinking: set[str],
    overflow_compacted: bool,
) -> Dict[str, Any]:
    raw_exec_data = exec_res.get("raw", {})
    exec_error = str(raw_exec_data.get("error") or "")
    if exec_error:
        error_kind = error_classifier.classify(exec_error)
        if error_kind == "context_overflow" and not overflow_compacted:
            _emit_loop_event(
                loop,
                session_id=session_id,
                goal_id=str(getattr(goal, "goal_id", "") or ""),
                event_type="compaction_start",
                category="compaction",
                phase="start",
                payload={"reason": "context_overflow", "attempt_index": int(metrics.get("total_attempts") or 0)},
            )
            print(f"⚠️ [Reflect] Context overflow detected. Attempting auto-compaction...")
            compacted = False
            session_store = getattr(loop, "session_store", None)
            session_policy = getattr(loop, "session_policy", None)
            if session_store is not None:
                try:
                    _, report = session_store.maybe_compact(session_id, policy=session_policy)
                    compacted = bool(report.compacted)
                except Exception:
                    compacted = False
            if not compacted:
                compact_res = await compact_session_context(
                    session_id=session_id,
                    memory_fabric=loop.memory_fabric,
                    model_router=loop.model_router,
                    domain=task.domain
                )
                compacted = bool(compact_res.get("compacted"))
            _emit_loop_event(
                loop,
                session_id=session_id,
                goal_id=str(getattr(goal, "goal_id", "") or ""),
                event_type="compaction_end",
                category="compaction",
                phase="end",
                payload={
                    "reason": "context_overflow",
                    "status": "compacted" if compacted else "not_compacted",
                    "attempt_index": int(metrics.get("total_attempts") or 0),
                },
            )
            if compacted:
                overflow_compacted = True
                print(f"✅ [Reflect] Compaction successful. Retrying same attempt with condensed context.")
                return {
                    "retry_same_attempt": True, "current_think_level": current_think_level,
                    "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
                    "last_error_msg": last_error_msg, "failure_count": failure_count,
                    "tool_only_no_update_count": tool_only_no_update_count, "latest_self_awareness": latest_self_awareness,
                    "final_output": "", "actions_summary": "", "should_break": False,
                }
        fallback_think = error_classifier.pick_fallback_thinking_level(exec_error, attempted_thinking)
        if fallback_think:
            print(f"⚠️ [Reflect] Thinking level '{current_think_level}' unsupported. Falling back to '{fallback_think}'...")
            return {
                "retry_same_attempt": True, "current_think_level": fallback_think,
                "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
                "last_error_msg": last_error_msg, "failure_count": failure_count,
                "tool_only_no_update_count": tool_only_no_update_count, "latest_self_awareness": latest_self_awareness,
                "final_output": "", "actions_summary": "", "should_break": False,
            }

    exec_res["_session_id"] = str(session_id or "global")
    exec_res["_turn_id"] = str(trace_id or "")
    final_output, actions_summary = loop._sanitize_executor_output(exec_res)
    _emit_loop_event(
        loop,
        session_id=session_id,
        goal_id=str(getattr(goal, "goal_id", "") or ""),
        event_type="message",
        category="message",
        phase="update",
        payload={
            "attempt_index": int(metrics.get("total_attempts") or 0),
            "final_output_preview": str(final_output or "")[:800],
            "actions_summary_preview": str(actions_summary or "")[:800],
        },
    )
    progressive_pressure = tool_only_no_update_count >= 3
    if progressive_pressure:
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.EXECUTION,
                    payload={
                        "attempt_index": metrics["total_attempts"],
                        "goal_id": goal.goal_id,
                        "progressive_pressure_triggered": True,
                        "tool_only_no_update_count": tool_only_no_update_count,
                    },
                )
            )
        except Exception:
            pass

    raw_err = exec_res.get("raw", {}).get("error") if isinstance(exec_res.get("raw"), dict) else None
    consecutive_errors, last_error_msg, current_err, triggered = loop._update_circuit_breaker_state(
        raw_error=raw_err, consecutive_errors=consecutive_errors, last_error_msg=last_error_msg, threshold=2,
    )
    if triggered:
        logger.error(f"CognitiveLoop: Circuit breaker triggered! Repeating error: {current_err}")
        
        # Strong Feedback Point #2b: Self-programming trigger must flow through hook
        try:
            hook = getattr(loop, "self_programming_hook", None)
            if hook is not None and hasattr(hook, "trigger_self_heal"):
                from quentin.cognitive.self_programming_hook import SelfProgrammingTrigger

                related_files = loop._get_candidate_files(task.input_text)
                session_id_for_hook = str(session_id or (task.metadata or {}).get("session_id") or task.task_id)
                hook.trigger_self_heal(
                    SelfProgrammingTrigger(
                        session_id=session_id_for_hook,
                        trace_id=str(trace_id),
                        goal_id=str(goal.goal_id),
                        task_id=str(task.task_id),
                        reason="circuit_breaker_repeating_system_error",
                        error=str(current_err or ""),
                        actions_summary=str(actions_summary or ""),
                        related_files=related_files,
                        meta={"consecutive_errors": int(consecutive_errors or 0)},
                    )
                )
        except Exception:
            pass

        final_output = f"Aborted due to repeated system error: {current_err}"
        try:
            loop.memory_fabric.remember_atomic(
                content=f"Circuit breaker triggered for goal {goal.goal_id}. Last error: {current_err}",
                source=f"cognitive_loop:cb:{task.task_id}",
                tier=MemoryTier.STS,
                importance=0.9,
                tags=["circuit_breaker", "failure"]
            )
        except Exception:
            pass
        return {
            "retry_same_attempt": False, "current_think_level": current_think_level,
            "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
            "last_error_msg": last_error_msg, "failure_count": failure_count,
            "tool_only_no_update_count": tool_only_no_update_count, "latest_self_awareness": latest_self_awareness,
            "final_output": final_output, "actions_summary": actions_summary, "should_break": True,
        }

    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION,
                payload={"attempt_index": metrics["total_attempts"], "goal_id": goal.goal_id, "raw": exec_res.get("raw")},
            )
        )
    except Exception:
        pass

    step_records = raw_exec_data.get("steps", [])
    
    # P1: Intercept Critical Failures (e.g., Tool Misuse)
    for s in (step_records or []):
        if not isinstance(s, dict): continue
        result = s.get("result")
        if isinstance(result, dict) and result.get("critical_failure"):
            err_code = result.get("error_code", "CRITICAL_TOOL_FAILURE")
            logger.warning(f"CognitiveLoop: CRITICAL FAILURE intercepted: {err_code}. Forcing reflection.")
            feedback = {
                "retry_same_attempt": False, "current_think_level": current_think_level,
                "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
                "last_error_msg": f"critical_failure:{err_code}", "failure_count": max(failure_count, 3), # Force reflection
                "tool_only_no_update_count": tool_only_no_update_count + 1, "latest_self_awareness": latest_self_awareness,
                "final_output": f"Critical Error: {result.get('error')}",
                "actions_summary": f"critical_failure_break: {err_code}", "should_break": True,
            }
            apply_feedback_to_runtime_state(state=state, feedback=feedback)
            return feedback

    # P0: Detect repetitive tool/model loops and run interrupt state machine.
    import hashlib
    current_attempt_calls = []
    for s in (step_records or []):
        if not isinstance(s, dict): continue
        result = s.get("result")
        if not isinstance(result, dict): continue
        call_tool = result.get("call_tool")
        if isinstance(call_tool, dict):
            # Create a stable fingerprint of the tool name and its arguments
            call_str = f"{call_tool.get('tool_name')}:{json.dumps(call_tool.get('arguments'), sort_keys=True)}"
            call_hash = hashlib.sha256(call_str.encode()).hexdigest()
            current_attempt_calls.append(call_hash)
    
    # Check if call sequence is repeating across attempts.
    attempt_signature = "|".join(current_attempt_calls)
    repeated_sig = ""
    if attempt_signature:
        state.call_history.append(attempt_signature)
        repeated_sig = detect_repetitive_sequence(state.call_history, window=3)

    model_repetition = bool(exec_res.get("repetition_detected"))
    if not model_repetition:
        err_hint = str(exec_res.get("error") or "").lower()
        model_repetition = ("repetition_detected" in err_hint) or ("model_repetition_detected" in err_hint)

    if repeated_sig:
        state.tool_loop_streak = int(state.tool_loop_streak or 0) + 1
    else:
        state.tool_loop_streak = 0
    if model_repetition:
        state.repetition_streak = int(state.repetition_streak or 0) + 1
    else:
        state.repetition_streak = 0
    error_subcategory, error_origin = _infer_interrupt_error_context(exec_res=exec_res)

    interrupt_state = _derive_attempt_interrupt_state(
        repetition_streak=state.repetition_streak,
        tool_loop_streak=state.tool_loop_streak,
    )
    if interrupt_state != "none":
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.CRITIC,
                    payload={
                        "attempt_index": metrics["total_attempts"],
                        "goal_id": goal.goal_id,
                        "attempt_interrupt_state": interrupt_state,
                        "tool_loop_streak": int(state.tool_loop_streak or 0),
                        "repetition_streak": int(state.repetition_streak or 0),
                        "repeated_tool_signature_detected": bool(repeated_sig),
                        "model_repetition_detected": bool(model_repetition),
                        "interrupt_error_subcategory": error_subcategory,
                        "interrupt_error_origin": error_origin,
                    },
                )
            )
        except Exception:
            pass
    if interrupt_state == "warn":
        actions_summary = (actions_summary + "\n" if actions_summary else "") + "interrupt_warn: loop/repetition risk rising"
    elif interrupt_state in {"interrupt", "hard_reset"}:
        logger.error(
            "CognitiveLoop: interrupt state=%s (tool_loop_streak=%s, repetition_streak=%s)",
            interrupt_state,
            state.tool_loop_streak,
            state.repetition_streak,
        )
        state.critical_instruction = (
            "INTERRUPT MODE: You are repeating ineffective behavior. "
            "Before any mutation, run fresh diagnostics (pwd/id/ls/fs.get_write_policy) and explain strategy delta. "
            "Do not replay prior tool sequence."
        )
        if interrupt_state == "hard_reset":
            state.last_plan_result = None
            state.critical_instruction = (
                "HARD RESET MODE: repeated loops persisted after interruption. "
                "Forget prior decomposition and restart from goal + physical evidence only. "
                "First step must be a user-visible progress sync, then bounded diagnostics, then a new branch."
            )
        assigned_cooldown = _adaptive_interrupt_cooldown_length(
            state=interrupt_state,
            error_subcategory=error_subcategory,
            error_origin=error_origin,
            repetition_streak=int(state.repetition_streak or 0),
            tool_loop_streak=int(state.tool_loop_streak or 0),
        )
        state.interrupt_cooldown_remaining = max(
            int(state.interrupt_cooldown_remaining or 0),
            assigned_cooldown,
        )
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.CRITIC,
                    payload={
                        "attempt_index": metrics["total_attempts"],
                        "goal_id": goal.goal_id,
                        "attempt_interrupt_state": interrupt_state,
                        "cooldown_assigned": int(state.interrupt_cooldown_remaining or 0),
                        "interrupt_error_subcategory": error_subcategory,
                        "interrupt_error_origin": error_origin,
                    },
                )
            )
        except Exception:
            pass
        feedback = {
            "retry_same_attempt": False, "current_think_level": current_think_level,
            "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
            "last_error_msg": "repeated_tool_call_loop", "failure_count": failure_count + 1,
            "tool_only_no_update_count": tool_only_no_update_count + 1, "latest_self_awareness": latest_self_awareness,
            "final_output": "", "actions_summary": f"interrupt_{interrupt_state}: strategy_breakout,cooldown={state.interrupt_cooldown_remaining}",
            "should_break": False,
        }
        apply_feedback_to_runtime_state(state=state, feedback=feedback)
        return feedback

    exec_success = raw_exec_data.get("success", False)
    anti_pattern = loop._detect_execution_antipattern(raw_exec_data=raw_exec_data)
    if anti_pattern.get("detected"):
        exec_success = False
        loop._cache_plan_override(goal, loop._build_antipattern_recovery_plan(task=task, anti_pattern=anti_pattern))
        actions_summary = (actions_summary + "\n" if actions_summary else "") + f"antipattern_recovery_queued: {anti_pattern.get('reason')}"
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.CRITIC,
                    payload={
                        "attempt_index": metrics["total_attempts"], "goal_id": goal.goal_id,
                        "antipattern_detected": anti_pattern.get("reason"), "target_path": anti_pattern.get("target_path"),
                    },
                )
            )
        except Exception:
            pass
    attempt_eval = evaluate_attempt_result(
        exec_res=exec_res,
        anti_pattern_detected=bool(anti_pattern.get("detected")),
    )
    attempt_eval_payload = attempt_eval.to_dict()
    exec_res["attempt_evaluation"] = attempt_eval_payload
    metrics["last_attempt_evaluation"] = attempt_eval_payload
    if isinstance(task.metadata, dict):
        task.metadata["last_attempt_evaluation"] = attempt_eval_payload
    try:
        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.CRITIC,
                payload={
                    "attempt_index": metrics["total_attempts"],
                    "goal_id": goal.goal_id,
                    "action": "attempt_evaluated",
                    "attempt_evaluation": attempt_eval_payload,
                },
            )
        )
    except Exception:
        pass
    if loop._is_tool_only_no_update(raw_exec_data=raw_exec_data, final_output=final_output):
        tool_only_no_update_count += 1
    else:
        tool_only_no_update_count = 0
    try:
        executed_skill_ids: List[str] = []
        for s in (step_records or []):
            if isinstance(s, dict) and s.get("skill_id"):
                executed_skill_ids.append(str(s.get("skill_id")))
        executed_skill_ids = sorted({s for s in executed_skill_ids if s})
        loop.session_delta_writer.observe_execution(
            session_id=session_id,
            trace_id=trace_id,
            attempt_index=metrics["total_attempts"],
            task_domain=task.domain,
            task_environment=task.environment,
            plan_summary=plan_summary,
            actions_summary=actions_summary,
            final_output=final_output,
            extra_metadata={
                "goal_id": getattr(goal, "goal_id", None),
                "situation_id": (task.metadata or {}).get("situation_id") if isinstance(task.metadata, dict) else None,
                "situation_confidence": (task.metadata or {}).get("situation_confidence") if isinstance(task.metadata, dict) else None,
                "attention_reduction_ratio": (task.metadata or {}).get("attention_reduction_ratio") if isinstance(task.metadata, dict) else None,
                "exec_success": bool(exec_success),
                "executed_skill_ids": executed_skill_ids,
            },
        )
    except Exception:
        pass

    attempt_metrics = loop._extract_attempt_metrics(raw_exec_data=raw_exec_data, attempt_start=attempt_started_at, attempt_end=now_utc())
    record_capability_gaps(
        loop,
        task=task,
        goal=goal,
        trace_id=trace_id,
        session_id=session_id,
        metrics=metrics,
        step_records=step_records if isinstance(step_records, list) else [],
    )
    if exec_success:
        metrics["success_attempts"] += 1
    else:
        metrics["error_attempts"] += 1
        failure_count += 1

    latest_self_awareness = self_awareness_engine.observe_attempt(
        exec_result=exec_res,
        metrics=metrics,
        degrade_mode=loop.degrade_mode,
        self_programming_enabled=loop.self_programming_enabled,
    )
    loop._emit_self_awareness_event(
        session_id=session_id,
        goal=goal,
        attempt_index=metrics["total_attempts"],
        snapshot=latest_self_awareness,
    )
    if (not anti_pattern.get("detected")) and latest_self_awareness.anti_pattern_reason:
        synthetic = {"detected": True, "reason": latest_self_awareness.anti_pattern_reason, "target_path": ""}
        loop._cache_plan_override(goal, loop._build_antipattern_recovery_plan(task=task, anti_pattern=synthetic))
        failure_count = max(failure_count, 2)
        actions_summary = (actions_summary + "\n" if actions_summary else "") + f"self_awareness_antipattern: {latest_self_awareness.anti_pattern_reason}"
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.CRITIC,
                    payload={
                        "attempt_index": metrics["total_attempts"],
                        "goal_id": goal.goal_id,
                        "self_awareness_antipattern": latest_self_awareness.anti_pattern_reason,
                    },
                )
            )
        except Exception:
            pass
    awareness_control = loop._apply_self_awareness_runtime_controls(latest_self_awareness)
    if awareness_control["request_flush"]:
        await loop._flush_memory(goal, session_id)
    if awareness_control["force_reflection"]:
        failure_count = max(failure_count, 3)
    if awareness_control["abort_now"]:
        reason = str(awareness_control["abort_reason"] or "self_awareness_abort")
        actions_summary = (actions_summary + "\n" if actions_summary else "") + f"self_awareness_abort: {reason}"
        final_output = final_output or f"Aborted by self-awareness guard: {reason}"
        return {
            "retry_same_attempt": False, "current_think_level": current_think_level,
            "overflow_compacted": overflow_compacted, "consecutive_errors": consecutive_errors,
            "last_error_msg": last_error_msg, "failure_count": failure_count,
            "tool_only_no_update_count": tool_only_no_update_count, "latest_self_awareness": latest_self_awareness,
            "final_output": final_output, "actions_summary": actions_summary, "should_break": True,
        }

    metrics["cost_tokens"] += attempt_metrics["cost_tokens"]
    metrics["latency_ms"] = attempt_metrics["latency_ms"]
    metrics["tool_call_count"] += int(attempt_metrics.get("tool_calls") or 0)
    metrics["prediction_error_count"] += int(attempt_metrics.get("prediction_errors") or 0)
    denom = float(metrics["tool_call_count"] or 0)
    metrics["prediction_error_rate"] = (float(metrics["prediction_error_count"] or 0) / denom if denom > 0 else 0.0)

    recent_traces.append({"attempt_index": metrics["total_attempts"], "steps": step_records})
    if len(recent_traces) > 5:
        del recent_traces[:-5]

    md = task.metadata or {}
    if not isinstance(md, dict):
        md = {}
    situation_id = md.get("situation_id")
    situation_confidence = md.get("situation_confidence")
    attention_reduction_ratio = md.get("attention_reduction_ratio")
    context_misclass_rate = None
    try:
        if situation_confidence is not None:
            conf = float(situation_confidence)
            metrics.setdefault("_context_low_conf_count", 0)
            if conf < 0.40:
                metrics["_context_low_conf_count"] = int(metrics["_context_low_conf_count"]) + 1
            context_misclass_rate = float(metrics.get("_context_low_conf_count") or 0) / float(metrics["total_attempts"] or 1)
    except Exception:
        context_misclass_rate = None

    snapshot = MetricSnapshot(
        attempt_index=metrics["total_attempts"],
        total_attempts=metrics["total_attempts"],
        success_attempts=metrics["success_attempts"],
        error_attempts=metrics["error_attempts"],
        cost_tokens=metrics["cost_tokens"],
        latency_ms=metrics["latency_ms"],
        reward_score=0.0,
        tool_call_count=int(metrics.get("tool_call_count") or 0),
        prediction_error_count=int(metrics.get("prediction_error_count") or 0),
        prediction_error_rate=float(metrics.get("prediction_error_rate") or 0.0),
        situation_id=str(situation_id) if situation_id else None,
        situation_confidence=float(situation_confidence) if situation_confidence is not None else None,
        attention_reduction_ratio=float(attention_reduction_ratio) if attention_reduction_ratio is not None else None,
        context_misclass_rate=context_misclass_rate,
    )
    recent_snapshots.append(snapshot)
    if len(recent_snapshots) > 10:
        del recent_snapshots[:-10]

    done_result, failure_count, should_break = evaluate_attempt_outcome(
        loop,
        task=task,
        goal=goal,
        trace_id=trace_id,
        loop_idx=loop_idx,
        metrics=metrics,
        plan_result=plan_result,
        plan_summary=plan_summary,
        exec_res=exec_res,
        final_output=final_output,
        actions_summary=actions_summary,
        snapshot=snapshot,
        recent_snapshots=recent_snapshots,
        recent_traces=recent_traces,
        latest_self_awareness=latest_self_awareness,
        failure_count=failure_count,
    )
    return {
        "retry_same_attempt": False,
        "current_think_level": current_think_level,
        "overflow_compacted": overflow_compacted,
        "consecutive_errors": consecutive_errors,
        "last_error_msg": last_error_msg,
        "failure_count": failure_count,
        "tool_only_no_update_count": tool_only_no_update_count,
        "latest_self_awareness": latest_self_awareness,
        "final_output": final_output,
        "actions_summary": actions_summary,
        "done_result": done_result,
        "should_break": should_break,
    }
