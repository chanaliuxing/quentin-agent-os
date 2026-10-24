from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _extract_explicit_task_paths(*, repo_root: Any, text: str) -> List[str]:
    raw = str(text or "")
    candidates: List[str] = []
    patterns = [
        r"`([^`\n]+)`",
        r"'([^'\n]+)'",
        r"\"([^\"\n]+)\"",
        r"(?<![\w/.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, raw):
            value = match if isinstance(match, str) else ""
            norm = str(value or "").strip().strip("/")
            if norm:
                candidates.append(norm)

    seen: set[str] = set()
    existing: List[str] = []
    missing: List[str] = []
    for rel in candidates:
        key = rel.lower()
        if key in seen:
            continue
        seen.add(key)
        p = (repo_root / rel).resolve()
        try:
            p.relative_to(repo_root)
        except Exception:
            continue
        rel_norm = str(p.relative_to(repo_root))
        if p.exists():
            existing.append(rel_norm)
        else:
            missing.append(rel_norm)
    return existing + missing


def _extract_primary_error_from_exec(last_exec_result: Dict[str, Any]) -> str:
    if not isinstance(last_exec_result, dict):
        return ""
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    direct = str(raw.get("error") or "").strip()
    if direct:
        return direct[:500]
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for s in reversed(steps):
        if not isinstance(s, dict):
            continue
        err = str(s.get("error") or "").strip()
        if err:
            return err[:500]
        res = s.get("result") if isinstance(s.get("result"), dict) else {}
        err2 = str(res.get("error") or "").strip()
        if err2:
            return err2[:500]
        tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
        err3 = str(tr.get("error") or "").strip()
        if err3:
            return err3[:500]
    return ""


def infer_pre_sensing_focus_paths(*, repo_root: Any, task: Any) -> List[str]:
    text = str(getattr(task, "input_text", "") or "")
    candidates: List[str] = _extract_explicit_task_paths(repo_root=repo_root, text=text)
    if "extensions/tools" in text or "plugin" in text.lower():
        candidates.append("extensions/tools")
    if "gemini_cli" in text:
        candidates.append("extensions/tools/gemini_cli")
    for path in re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]*", text):
        norm = path.strip().strip("/")
        if norm:
            candidates.append(norm)
    if not candidates:
        candidates = ["extensions/tools", "mutable", "generated"]

    seen = set()
    out: List[str] = []
    for rel in candidates:
        key = rel.lower()
        if key in seen:
            continue
        seen.add(key)
        p = (repo_root / rel).resolve()
        try:
            p.relative_to(repo_root)
        except Exception:
            continue
        out.append(str(p.relative_to(repo_root)))
        if len(out) >= 6:
            break
    return out


def infer_focus_paths_from_last_execution(*, last_exec_result: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if not isinstance(last_exec_result, dict) or not last_exec_result:
        return out
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for s in steps[-12:]:
        if not isinstance(s, dict):
            continue
        result = s.get("result") if isinstance(s.get("result"), dict) else {}
        call_tool = result.get("call_tool") if isinstance(result.get("call_tool"), dict) else {}
        args = call_tool.get("arguments") if isinstance(call_tool.get("arguments"), dict) else {}
        for k in ("path", "file", "target_path", "dir", "directory"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip().strip("/"))
        cmd = args.get("command")
        if isinstance(cmd, str) and "extensions/tools" in cmd:
            out.append("extensions/tools")
        if isinstance(cmd, str) and "gemini_cli" in cmd:
            out.append("extensions/tools/gemini_cli")
    seen: set[str] = set()
    deduped: List[str] = []
    for p in out:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
        if len(deduped) >= 6:
            break
    return deduped


def refresh_planner_environment_snapshot(
    loop: Any,
    *,
    task: Any,
    last_exec_result: Dict[str, Any],
) -> Tuple[str, List[str]]:
    focus_paths_for_planner: List[str] = []
    try:
        base_focus = loop._infer_pre_sensing_focus_paths(task)
        exec_focus = loop._infer_focus_paths_from_last_execution(last_exec_result)
        merged = base_focus + exec_focus
        seen: set[str] = set()
        for p in merged:
            key = str(p).strip().strip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            focus_paths_for_planner.append(str(p).strip().strip("/"))
            if len(focus_paths_for_planner) >= 8:
                break
        env_snapshot = loop._get_environment_snapshot(
            focus_paths=focus_paths_for_planner,
            focused_only=False,
            max_lines=int(os.getenv("QUENTIN_PLANNER_ENV_MAX_LINES", "300") or "300"),
            task=task,
        )
        return env_snapshot, focus_paths_for_planner
    except Exception:
        return loop._get_environment_snapshot(task=task), []


def build_base_planner_context(
    loop: Any,
    *,
    task: Any,
    historical_context: str,
    env_snapshot: str,
    focus_paths_for_planner: List[str],
    last_exec_result: Dict[str, Any],
    last_plan_result: Optional[Any],
    latest_self_awareness: Any,
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
    from quentin.cognitive.self_awareness import SelfAwarenessEngine
    from quentin.cognitive.planning_payload_matrix import derive_planner_lifecycle_payload
    from quentin.cognitive.planning_strategy_patch import derive_planning_strategy_patch
    from quentin.cognitive.planning_retry_delta import derive_retry_plan_delta
    from quentin.cognitive.planning_payload_variants import derive_planner_payload_variant
    from quentin.memory.kinds import KIND_TOOL_KNOWLEDGE

    attempt_eval = last_exec_result.get("attempt_evaluation") if isinstance(last_exec_result, dict) else {}
    if not isinstance(attempt_eval, dict):
        attempt_eval = {}
    previous_error = _extract_primary_error_from_exec(last_exec_result)
    retry_error_patch = ""
    if int(attempt_index or 1) > 1 and previous_error:
        retry_error_patch = (
            "RETRY ERROR PATCH:\n"
            f"- previous_error: {previous_error}\n"
            f"- previous_category: {attempt_eval.get('category')}\n"
            "You must explain how this plan differs from the failed path."
        )
    lifecycle_payload = derive_planner_lifecycle_payload(
        context={
            "attempt_index": int(attempt_index or 1),
            "failure_count": int(failure_count or 0),
            "tool_only_no_update_count": int(tool_only_no_update_count or 0),
            "retry_budget_remaining": float(retry_budget_remaining or 0.0),
            "last_attempt_evaluation": attempt_eval,
            "previous_error": previous_error,
        }
    ).to_dict()
    strategy_patch_obj = derive_planning_strategy_patch(
        context={
            "attempt_index": int(attempt_index or 1),
            "failure_count": int(failure_count or 0),
            "tool_only_no_update_count": int(tool_only_no_update_count or 0),
            "retry_budget_remaining": float(retry_budget_remaining or 0.0),
            "last_attempt_evaluation": attempt_eval,
            "planner_lifecycle_payload": lifecycle_payload,
        }
    )
    strategy_patch = strategy_patch_obj.to_dict() if strategy_patch_obj else {}
    strategy_patch_text = str(strategy_patch.get("prompt_patch") or "").strip() if isinstance(strategy_patch, dict) else ""
    previous_plan_steps = (last_plan_result.steps if last_plan_result else [])
    retry_plan_delta_obj = derive_retry_plan_delta(
        attempt_index=int(attempt_index or 1),
        previous_plan_steps=previous_plan_steps if isinstance(previous_plan_steps, list) else [],
        last_exec_result=last_exec_result if isinstance(last_exec_result, dict) else {},
    )
    retry_plan_delta = retry_plan_delta_obj.to_dict() if retry_plan_delta_obj else {}
    retry_plan_delta_patch = str(retry_plan_delta.get("prompt_patch") or "").strip() if isinstance(retry_plan_delta, dict) else ""
    payload_variant = derive_planner_payload_variant(
        context={
            "planner_lifecycle_payload": lifecycle_payload,
            "last_attempt_evaluation": attempt_eval,
            "last_exec_result": last_exec_result if isinstance(last_exec_result, dict) else {},
        }
    )
    payload_variant_patch = str(payload_variant.get("prompt_patch") or "").strip() if isinstance(payload_variant, dict) else ""

    # ---- Strong Feedback Point #1: Planner Input Context Enrichment ----
    # - Skills: lightweight, sync-safe suggestions (SOP/markdown matching).
    skill_suggestions: List[Dict[str, Any]] = []
    try:
        sm = getattr(loop, "skill_manager", None)
        if sm is not None and hasattr(sm, "match_markdown_skills"):
            top_k = int(os.getenv("QUENTIN_PLANNER_SKILL_SUGGEST_TOP_K", "5") or "5")
            raw = sm.match_markdown_skills(task.input_text, top_k=top_k)
            for item in raw or []:
                if not isinstance(item, dict):
                    continue
                skill_suggestions.append(
                    {
                        "skill_id": item.get("skill_id"),
                        "name": item.get("name"),
                        "description": item.get("description"),
                        "domain": item.get("domain"),
                        "score": item.get("score"),
                    }
                )
            skill_suggestions = skill_suggestions[: max(1, top_k)]
    except Exception:
        skill_suggestions = []

    # - Tools: schema summaries + learned tool usage (tool_knowledge).
    tool_menu = ""
    tool_summaries: Dict[str, str] = {}
    tool_knowledge: List[Dict[str, Any]] = []
    try:
        tm = getattr(loop, "tool_manager", None)
        if tm is not None and hasattr(tm, "get_tool_menu"):
            menu_ctx = {
                "session_id": str((task.metadata or {}).get("session_id") or task.task_id or "default"),
                "domain": str(getattr(task, "domain", "") or "core"),
                "environment": str(getattr(task, "environment", "") or "sandbox"),
                "channel": str((task.metadata or {}).get("channel") or (task.metadata or {}).get("gateway_channel") or ""),
                "provider": str((task.metadata or {}).get("llm_provider") or ""),
            }
            tool_menu = str(tm.get_tool_menu(context_metadata=menu_ctx) or "")
            if len(tool_menu) > 5000:
                tool_menu = tool_menu[:4997] + "..."
        if tm is not None and hasattr(tm, "get_tool_summaries"):
            sum_ctx = {
                "session_id": str((task.metadata or {}).get("session_id") or task.task_id or "default"),
                "domain": str(getattr(task, "domain", "") or "core"),
                "environment": str(getattr(task, "environment", "") or "sandbox"),
                "channel": str((task.metadata or {}).get("channel") or (task.metadata or {}).get("gateway_channel") or ""),
                "provider": str((task.metadata or {}).get("llm_provider") or ""),
                "role": str((task.metadata or {}).get("role") or ""),
                "group": str((task.metadata or {}).get("group") or ""),
                "groups": list((task.metadata or {}).get("groups") or []) if isinstance((task.metadata or {}).get("groups"), list) else [],
            }
            tool_summaries = dict(tm.get_tool_summaries(max_words=12, context_metadata=sum_ctx) or {})
    except Exception:
        tool_menu = ""
        tool_summaries = {}
    try:
        mf = getattr(loop, "memory_fabric", None)
        if mf is not None:
            from quentin.memory.models import MemoryQuery, MemoryTier

            known = None
            tm = getattr(loop, "tool_manager", None)
            if tm is not None and hasattr(tm, "get_tool_names_by_domain"):
                try:
                    known = set(tm.get_tool_names_by_domain(str(getattr(task, "domain", "") or "core")) or [])
                except Exception:
                    known = None

            recs = mf.recall(
                MemoryQuery(
                    text="",
                    tier=MemoryTier.LTS,
                    kind=KIND_TOOL_KNOWLEDGE,
                    top_k=int(os.getenv("QUENTIN_PLANNER_TOOL_KNOWLEDGE_TOP_K", "4") or "4"),
                )
            )
            for r in recs or []:
                md = dict(getattr(r, "metadata", None) or {})
                tool_name = str(md.get("tool_name") or md.get("tool_id") or "").strip()
                if not tool_name:
                    continue
                if isinstance(known, set) and known and tool_name not in known:
                    continue
                stats = md.get("stats") if isinstance(md.get("stats"), dict) else {}
                tool_knowledge.append(
                    {
                        "tool_name": tool_name,
                        "success_rate": float(stats.get("success_rate") or 0.0),
                        "call_count": int(stats.get("call_count") or 0),
                        "last_used_at": str(stats.get("last_used_at") or ""),
                        "description": str(md.get("description") or "")[:240],
                        "examples": list(md.get("examples") or [])[:2] if isinstance(md.get("examples"), list) else [],
                    }
                )
            tool_knowledge = tool_knowledge[:6]
    except Exception:
        tool_knowledge = []

    return {
        "historical_attempts": historical_context,
        "current_environment_tree": env_snapshot,
        "focus_paths_used": focus_paths_for_planner,
        "last_execution": loop._compact_last_execution_for_planner(last_exec_result),
        "candidate_files": loop._get_candidate_files(task.input_text),
        "forbidden_actions": forbidden_actions,
        "previous_plan_steps": previous_plan_steps,
        "system_event_prompt": event_hint,
        "is_subagent": bool((task.metadata or {}).get("is_subagent", False)),
        "self_awareness": latest_self_awareness.to_dict(),
        "self_awareness_note": SelfAwarenessEngine.to_prompt_hint(latest_self_awareness),
        "current_vision": perception_data.get("screenshot"),
        "current_ui_tree": perception_data.get("ui_tree"),
        "critical_instruction": critical_instruction,
        "last_attempt_evaluation": attempt_eval,
        "planner_lifecycle_payload": lifecycle_payload,
        "attempt_index": int(attempt_index or 1),
        "failure_count": int(failure_count or 0),
        "tool_only_no_update_count": int(tool_only_no_update_count or 0),
        "retry_budget_remaining": float(retry_budget_remaining or 0.0),
        "interrupt_cooldown_remaining": int(interrupt_cooldown_remaining or 0),
        "interrupt_cooldown_active": bool(int(interrupt_cooldown_remaining or 0) > 0),
        "retry_error_patch": retry_error_patch,
        "planning_strategy_patch": strategy_patch,
        "planning_strategy_patch_text": strategy_patch_text,
        "retry_plan_delta": retry_plan_delta,
        "retry_plan_delta_patch": retry_plan_delta_patch,
        "planner_payload_variant": payload_variant,
        "planner_payload_variant_patch": payload_variant_patch,
        "previous_error": previous_error,
        "skill_suggestions": skill_suggestions,
        "tool_menu": tool_menu,
        "tool_summaries": tool_summaries,
        "tool_knowledge": tool_knowledge,
    }


def drain_system_events_for_planner(loop: Any, *, session_id: str) -> str:
    if not loop._system_events_enabled():
        return ""
    try:
        scoped = loop.system_event_queue.drain_events(session_id=session_id, limit=12)
        global_events = loop.system_event_queue.drain_events(session_id="global", limit=12)
        events = scoped + global_events
        if not events:
            return ""
        from quentin.runtime.system_events import SystemEventQueue
        from quentin.traces.core import TraceEventType, new_trace_event
        from meta_agent.config.feature_flags import PROMPT_MIGRATION_SYSTEM_EVENT_INJECTED

        text = SystemEventQueue.format_events_for_prompt(events, max_chars=2400)
        try:
            loop.trace_recorder.record_event(
                new_trace_event(
                    trace_id=f"system-events::{session_id}",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": PROMPT_MIGRATION_SYSTEM_EVENT_INJECTED,
                        "session_id": session_id,
                        "count": len(events),
                    },
                )
            )
        except Exception:
            pass
        return text
    except Exception:
        logger.exception("CognitiveLoop: failed to drain system events for planner")
        return ""


def emit_self_awareness_event(
    loop: Any,
    *,
    session_id: str,
    goal: Any,
    attempt_index: int,
    snapshot: Any,
) -> None:
    if snapshot.status not in {"warning", "critical"}:
        return
    payload = {
        "goal_id": str(getattr(goal, "goal_id", "") or ""),
        "attempt_index": int(attempt_index or 0),
        "status": str(snapshot.status or ""),
        "failure_rate": float(snapshot.failure_rate or 0.0),
        "failover_reason": str(snapshot.failover_reason or ""),
        "anti_pattern_reason": str(snapshot.anti_pattern_reason or ""),
        "consecutive_system_errors": int(snapshot.consecutive_system_errors or 0),
        "consecutive_no_progress": int(snapshot.consecutive_no_progress or 0),
        "suggested_actions": list(snapshot.suggested_actions or [])[:6],
    }
    try:
        loop.system_event_queue.enqueue_event(
            session_id=str(session_id or "global"),
            event_type="self_awareness_alert",
            payload=payload,
            source="cognitive_loop",
        )
    except Exception:
        logger.exception("CognitiveLoop: failed to enqueue self_awareness_alert event")
