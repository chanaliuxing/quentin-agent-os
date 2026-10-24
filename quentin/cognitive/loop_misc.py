from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional


def build_effective_planner_context(*, task: Any, planner_ctx: Dict[str, Any]) -> Dict[str, Any]:
    effective_ctx = dict(planner_ctx)
    if isinstance(task.metadata, dict):
        for key in ("url", "window_title", "app_name", "ui_tree", "logs_excerpt"):
            if key in task.metadata and key not in effective_ctx:
                effective_ctx[key] = task.metadata.get(key)
    effective_ctx["domain"] = task.domain
    effective_ctx["environment"] = task.environment
    return effective_ctx


def update_task_from_perception_snapshot(*, task: Any, perception_snapshot: Any) -> None:
    task.metadata["situation_id"] = perception_snapshot.situation.situation_id
    task.metadata["situation_confidence"] = perception_snapshot.situation.confidence
    task.metadata["attention_reduction_ratio"] = (
        perception_snapshot.attention.reduction_ratio if perception_snapshot.attention else None
    )


def apply_attention_context(*, loop: Any, planner_ctx: Dict[str, Any], perception_snapshot: Optional[Any]) -> Dict[str, Any]:
    if perception_snapshot is None or perception_snapshot.attention is None:
        return planner_ctx
    try:
        if not bool(getattr(loop.perception_layer.config, "debug_use_full_context", False)):
            narrowed = dict(perception_snapshot.attention.selected_context or {})
            narrowed.setdefault("attention_reduction_ratio", perception_snapshot.attention.reduction_ratio)
            narrowed.setdefault("attention_debug", perception_snapshot.attention.debug_refs)
            return narrowed
        planner_ctx["attention_reduction_ratio"] = perception_snapshot.attention.reduction_ratio
        planner_ctx["attention_debug"] = perception_snapshot.attention.debug_refs
        return planner_ctx
    except Exception:
        return planner_ctx


def sanitize_executor_output(*, loop: Any, exec_res: Dict[str, Any], logger: Any) -> tuple[str, str]:
    from quentin.infra.text.hygiene import TranscriptHygiene
    from quentin.runtime.silent_protocol import is_silent_reply

    direct_sent = exec_res.get("direct_response_sent", False)
    if direct_sent:
        logger.info("CognitiveLoop: Direct response sent by tool. Suppressing redundant final_output.")
        final_output = ""
    else:
        final_output = str(exec_res.get("final_output") or "")

    executor = getattr(loop, "executor", None)
    if hasattr(executor, "_strip_thinking_tags"):
        final_output = executor._strip_thinking_tags(final_output)

    final_output, _parsed = process_output_via_stream_protocol(
        loop=loop,
        raw_text=TranscriptHygiene.collapse_duplicates(str(final_output or "")),
        session_id=str(exec_res.get("_session_id") or "global"),
        turn_id=str(exec_res.get("_turn_id") or ""),
        logger=logger,
        meta={"direct_response_sent": bool(direct_sent)},
        is_silent_reply_fn=is_silent_reply,
    )

    actions_summary = str(exec_res.get("actions_summary") or "")
    return final_output, actions_summary


def process_output_via_stream_protocol(
    *,
    loop: Any,
    raw_text: str,
    session_id: str,
    turn_id: str,
    logger: Any,
    meta: Optional[Dict[str, Any]] = None,
    is_silent_reply_fn: Optional[Any] = None,
) -> tuple[str, Any]:
    from quentin.runtime.silent_protocol import is_silent_reply
    from quentin.runtime.stream_protocol import StreamChunker
    from quentin.runtime.event_protocol import EventProtocol

    checker = is_silent_reply_fn or is_silent_reply
    chunker = StreamChunker(max_chunk_chars=220)
    parsed = chunker.process(str(raw_text or ""))

    visible = str(parsed.visible_text or "").strip()
    if parsed.directives.silent or checker(visible):
        visible = ""

    queue = getattr(loop, "system_event_queue", None)
    if queue is not None:
        try:
            EventProtocol(queue=queue, source="cognitive.loop").emit_message_stream(
                session_id=str(session_id or "global"),
                turn_id=str(turn_id or ""),
                stream=parsed,
                meta=dict(meta or {}),
            )
        except Exception:
            logger.debug("process_output_via_stream_protocol: failed to emit stream events", exc_info=True)
    return visible, parsed


def prune_context_for_focus(*, context: Dict[str, Any], iteration: int) -> Dict[str, Any]:
    pruned = context.copy()
    if iteration == 1:
        pruned.pop("planner_repairs", None)
    tree_size = len(str(pruned.get("env_snapshot", "")))
    if tree_size > 20000:
        pruned["memories"] = []
    return pruned


def strict_reason_list_from_env() -> List[str]:
    raw = str(os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS", "") or "").strip()
    if not raw:
        return []
    parts: List[str] = []
    for item in raw.split(","):
        value = item.strip()
        if value:
            parts.append(value)
    return parts


def strict_reason_hint_from_env() -> str:
    parts = strict_reason_list_from_env()
    if not parts:
        return ""
    return "INTELLIGENCE STRICT REASONS: " + ", ".join(parts[:8]) + ". Prioritize discovery and low-risk, incremental steps."


def should_trigger_reflection(*, failure_count: int, metrics: Optional[Dict[str, Any]] = None) -> bool:
    enabled = str(os.getenv("QUENTIN_REFLECTION_ENABLED", "1") or "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False
    threshold = max(1, int(os.getenv("QUENTIN_REFLECTION_FAILURE_THRESHOLD", "3") or "3"))
    eval_data = metrics.get("last_attempt_evaluation") if isinstance(metrics, dict) and isinstance(metrics.get("last_attempt_evaluation"), dict) else {}
    severity = str(eval_data.get("severity") or "").strip().lower()
    if severity == "critical":
        threshold = min(threshold, 1)
    elif severity == "high":
        threshold = min(threshold, 2)

    retry_budget_remaining = float(metrics.get("retry_budget_remaining", 0.0) or 0.0) if isinstance(metrics, dict) else 0.0
    if retry_budget_remaining > 0 and retry_budget_remaining <= 1.0:
        threshold = min(threshold, 2)

    return failure_count >= threshold


def build_planner_result_from_reflection(*, planner_result_cls: Any, goal: Any, plan_obj: Dict[str, Any]) -> Any:
    raw_steps = plan_obj.get("steps") or []
    steps_list = []
    for idx, step in enumerate(raw_steps, start=1):
        steps_list.append(
            {
                "step_id": step.get("step_id") or f"s{idx}",
                "description": step.get("description") or "",
                "skill_id": step.get("skill_id"),
                "notes": step.get("notes"),
            }
        )
    return planner_result_cls(
        goal_id=goal.goal_id,
        raw_output=json.dumps(plan_obj, ensure_ascii=False),
        steps=steps_list,
        used_skills=[],
    )


def cache_plan_override(*, loop: Any, goal: Any, plan_obj: Dict[str, Any]) -> None:
    if not hasattr(loop, "_planner_overrides"):
        loop._planner_overrides = {}
    loop._planner_overrides[goal.goal_id] = plan_obj


def get_plan_override_if_any(*, loop: Any, goal: Any) -> Optional[Dict[str, Any]]:
    if hasattr(loop, "_planner_overrides"):
        return loop._planner_overrides.get(goal.goal_id)
    return None


def enqueue_skill_ideas_from_reflection(*, loop: Any, goal: Any, ideas: List[Dict[str, Any]], logger: Any) -> None:
    try:
        payload = {"goal_id": goal.goal_id, "ideas": ideas}
        out_dir = loop.repo_root / "data" / "reflection_skill_ideas"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{uuid.uuid4().hex}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("CognitiveLoop: failed to persist reflection skill ideas.")
