from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class AttemptEvaluation:
    category: str  # success | tool_execution_error | logic_path_error | plan_execution_misalignment | system_error | mixed
    correction_intensity: str  # low | medium | high | critical
    correction_score: float
    severity: str  # low | medium | high | critical
    retry_cost: float
    error_origin: str  # model | environment | mixed | system | none
    rationale: str
    error_subcategory: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _has_tool_execution_error(step_records: List[Dict[str, Any]]) -> bool:
    for step in step_records:
        if not isinstance(step, dict):
            continue
        res = step.get("result") if isinstance(step.get("result"), dict) else {}
        tool_res = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
        if tool_res and not bool(tool_res.get("success", True)):
            return True
        if bool(res.get("critical_failure")):
            return True
        # Some failures are "logic loop" failures, not tool execution failures.
        # Do not classify those as tool_execution_error, or we lose the ability to
        # distinguish "tool wrong" vs "path wrong" (OpenClaw attempt.ts parity).
        loop_markers = (
            "repeated_tool_call_loop",
            "no_progress_threshold_reached",
            "max_step_iterations_reached",
            "model_repetition_detected",
            "repetition_detected",
            "strategy_guard",
            "antipattern",
            "loop_detected",
        )
        err = str(step.get("error") or res.get("error") or "").strip().lower()
        if err and any(m in err for m in loop_markers):
            continue
        if step.get("success") is False:
            return True
        err = str(step.get("error") or res.get("error") or "").strip().lower()
        if err and any(k in err for k in ("permission denied", "not found", "validation", "blocked", "denied")):
            return True
    return False


def _has_logic_path_error(raw_exec_data: Dict[str, Any], actions_summary: str, anti_pattern: bool) -> bool:
    hay = " ".join(
        [
            str(actions_summary or ""),
            str(raw_exec_data.get("error") or ""),
            str(raw_exec_data.get("steps") or ""),
        ]
    ).lower()
    if anti_pattern:
        return True
    markers = (
        "repeated_tool_call_loop",
        "repetition_detected",
        "model_repetition_detected",
        "no_progress_threshold_reached",
        "max_step_iterations_reached",
        "antipattern",
        "loop_detected",
        "strategy_guard",
    )
    return any(m in hay for m in markers)


def _collect_error_text(exec_res: Dict[str, Any]) -> str:
    raw = exec_res.get("raw") if isinstance(exec_res.get("raw"), dict) else {}
    parts = [str(exec_res.get("actions_summary") or ""), str(raw.get("error") or "")]
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for s in steps:
        if not isinstance(s, dict):
            continue
        parts.append(str(s.get("error") or ""))
        res = s.get("result") if isinstance(s.get("result"), dict) else {}
        parts.append(str(res.get("error") or ""))
        tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
        parts.append(str(tr.get("error") or ""))
    return " | ".join(parts).lower()


def _classify_error_origin(exec_res: Dict[str, Any]) -> tuple[str, str]:
    text = _collect_error_text(exec_res)
    # Model-origin syntax/format failures
    model_markers = (
        "syntaxerror",
        "syntax error",
        "jsondecodeerror",
        "parse_failure",
        "invalid json",
        "format",
        "unexpected token",
        "indentationerror",
    )
    # Environment/runtime failures
    env_markers = (
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "rate limit",
        "429",
        "disk full",
        "permission denied",
        "resource busy",
        "no space left",
    )
    has_model = any(m in text for m in model_markers)
    has_env = any(m in text for m in env_markers)
    if has_model and has_env:
        return "mixed", "mixed_model_environment"
    if has_env:
        if "timeout" in text or "timed out" in text:
            return "environment", "environment_timeout_error"
        return "environment", "environment_runtime_error"
    if has_model:
        return "model", "model_syntax_error"
    return "none", "unclassified_error"


def evaluate_attempt_result(
    *,
    exec_res: Dict[str, Any],
    anti_pattern_detected: bool = False,
) -> AttemptEvaluation:
    from quentin.cognitive.tool_error_subtypes import classify_tool_error_subtype

    raw = exec_res.get("raw") if isinstance(exec_res.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    step_records = [s for s in steps if isinstance(s, dict)]
    is_system_error = bool(exec_res.get("is_system_error", False))
    success = bool(raw.get("success", False))
    actions_summary = str(exec_res.get("actions_summary") or "")
    _, error_subcategory = classify_tool_error_subtype(last_exec_result=exec_res)

    if is_system_error:
        return AttemptEvaluation(
            category="system_error",
            correction_intensity="critical",
            correction_score=1.0,
            severity="critical",
            retry_cost=2.5,
            error_origin="system",
            error_subcategory=error_subcategory,
            rationale="System-level failure detected; require maximum correction intensity.",
        )
    if success:
        return AttemptEvaluation(
            category="success",
            correction_intensity="low",
            correction_score=0.15,
            severity="low",
            retry_cost=0.25,
            error_origin="none",
            error_subcategory="",
            rationale="Execution succeeded; only lightweight correction needed.",
        )

    if error_subcategory == "plan_execution_misalignment":
        return AttemptEvaluation(
            category="plan_execution_misalignment",
            correction_intensity="high",
            correction_score=0.82,
            severity="high",
            retry_cost=1.75,
            error_origin="mixed",
            error_subcategory=error_subcategory,
            rationale="Planner step and executor tool call misaligned; force strategy reset and stronger tool alignment guard.",
        )

    tool_error = _has_tool_execution_error(step_records)
    logic_error = _has_logic_path_error(raw, actions_summary, anti_pattern_detected)
    origin, origin_category = _classify_error_origin(exec_res)

    if origin_category == "environment_timeout_error":
        return AttemptEvaluation(
            category="environment_timeout_error",
            correction_intensity="critical",
            correction_score=0.95,
            severity="critical",
            retry_cost=2.0,
            error_origin=origin,
            error_subcategory=error_subcategory,
            rationale="Environment timeout/deadlock detected; consume retry budget aggressively.",
        )
    if origin_category == "model_syntax_error":
        return AttemptEvaluation(
            category="model_syntax_error",
            correction_intensity="medium",
            correction_score=0.60,
            severity="medium",
            retry_cost=1.0,
            error_origin=origin,
            error_subcategory=error_subcategory,
            rationale="Model output/format/syntax failure detected; retry with tighter format guidance.",
        )

    if tool_error and logic_error:
        return AttemptEvaluation(
            category="mixed",
            correction_intensity="high",
            correction_score=0.85,
            severity="high",
            retry_cost=1.75,
            error_origin=origin if origin != "none" else "mixed",
            error_subcategory=error_subcategory,
            rationale="Detected both tool execution failure and logical path failure.",
        )
    if tool_error:
        return AttemptEvaluation(
            category="tool_execution_error",
            correction_intensity="medium",
            correction_score=0.55,
            severity="medium",
            retry_cost=1.0,
            error_origin=origin if origin != "none" else "environment",
            error_subcategory=error_subcategory,
            rationale="Primary failure from tool execution/validation; planner should tighten execution guardrails.",
        )
    return AttemptEvaluation(
        category="logic_path_error",
        correction_intensity="high",
        correction_score=0.75,
        severity="high",
        retry_cost=1.25,
        error_origin=origin if origin != "none" else "model",
        error_subcategory=error_subcategory,
        rationale="Primary failure from strategy/path selection; planner should increase replanning correction pressure.",
    )
