from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from quentin.memory.models import MemoryTier
from quentin.memory.kinds import KIND_GIST_MEMORY, KIND_LESSON, KIND_CAPABILITY_ACQUISITION_REQUEST
from quentin.traces.core import LessonsLearned


def _safe_str(val: Any, limit: int) -> str:
    text = str(val or "")
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _extract_primary_error(last_exec_result: Dict[str, Any]) -> str:
    if not isinstance(last_exec_result, dict):
        return ""
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    err = str(raw.get("error") or "").strip()
    if err:
        return err[:600]
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for step in reversed(steps or []):
        if not isinstance(step, dict):
            continue
        res = step.get("result") if isinstance(step.get("result"), dict) else {}
        err2 = str(step.get("error") or res.get("error") or "").strip()
        if err2:
            return err2[:600]
    return ""


def build_task_lesson_content(
    *,
    done: bool,
    done_confidence: float,
    domain: str,
    environment: str,
    actions_summary: str,
    final_output: str,
    primary_error: str,
) -> str:
    status = "success" if done else "failed"
    lines: List[str] = [
        f"status: {status}",
        f"confidence: {done_confidence:.2f}",
        f"domain: {domain}",
        f"environment: {environment}",
    ]
    if primary_error:
        lines.append(f"primary_error: {_safe_str(primary_error, 380)}")
    if actions_summary:
        lines.append(f"actions: {_safe_str(actions_summary, 520)}")
    if final_output:
        lines.append(f"result: {_safe_str(final_output, 520)}")
    return "\n".join([x for x in lines if x])


def build_task_gist_lines(
    *,
    done: bool,
    domain: str,
    actions_summary: str,
    final_output: str,
) -> List[str]:
    gist: List[str] = []
    gist.append(f"Outcome: {'done' if done else 'not_done'} ({domain})")
    if actions_summary:
        actions_one_line = actions_summary.replace("\n", " ")
        gist.append(f"Actions: {_safe_str(actions_one_line, 180)}")
    if final_output:
        final_output_one_line = final_output.replace("\n", " ")
        gist.append(f"Result: {_safe_str(final_output_one_line, 180)}")
    return gist[:4]


def write_task_lessons_and_gist(
    loop: Any,
    *,
    session_id: str,
    trace_id: str,
    task: Any,
    goal: Any,
    plan_summary: str,
    actions_summary: str,
    final_output: str,
    done_result: Optional[Any],
    last_exec_result: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Strong Feedback Point #3: Done/Reflection writeback.

    Writes:
    - kind=lesson (STS) for planner-side reuse
    - kind=gist_memory (STS) for compact planner-side recall
    - trace_recorder.lessons.jsonl entry (best-effort)
    """
    mf = getattr(loop, "memory_fabric", None)
    tr = getattr(loop, "trace_recorder", None)
    if mf is None:
        return None, None

    done = bool(getattr(done_result, "is_done", False)) if done_result is not None else False
    conf = float(getattr(done_result, "confidence", 0.0) or 0.0) if done_result is not None else 0.0
    domain = str(getattr(task, "domain", "") or "core")
    environment = str(getattr(task, "environment", "") or "sandbox")
    primary_error = _extract_primary_error(last_exec_result)

    lesson_content = build_task_lesson_content(
        done=done,
        done_confidence=conf,
        domain=domain,
        environment=environment,
        actions_summary=actions_summary,
        final_output=final_output,
        primary_error=primary_error,
    )
    gist_lines = build_task_gist_lines(
        done=done,
        domain=domain,
        actions_summary=actions_summary,
        final_output=final_output,
    )

    lesson_id: Optional[str] = None
    gist_id: Optional[str] = None
    try:
        rec = mf.remember_atomic(
            content=lesson_content,
            source=f"cognitive_loop:lesson:{getattr(task, 'task_id', '')}",
            tier=MemoryTier.STS,
            importance=max(0.1, min(0.9, conf if done else 0.65)),
            tags=["lesson", "reflection", domain, environment, f"session:{session_id}"],
            kind=KIND_LESSON,
            domain=domain,
            metadata={
                "trace_id": trace_id,
                "task_id": getattr(task, "task_id", ""),
                "goal_id": getattr(goal, "goal_id", ""),
                "done": done,
                "done_confidence": conf,
                "plan_summary": _safe_str(plan_summary, 1200),
                "primary_error": primary_error,
            },
        )
        lesson_id = getattr(rec, "id", None)
    except Exception:
        lesson_id = None

    try:
        rec2 = mf.remember_atomic(
            content="\n".join(gist_lines),
            source=f"cognitive_loop:gist:{getattr(task, 'task_id', '')}",
            tier=MemoryTier.STS,
            importance=max(0.1, min(0.8, conf if done else 0.55)),
            tags=["gist", "task", domain, environment, f"session:{session_id}"],
            kind=KIND_GIST_MEMORY,
            domain=domain,
            metadata={
                "trace_id": trace_id,
                "task_id": getattr(task, "task_id", ""),
                "goal_id": getattr(goal, "goal_id", ""),
                "done": done,
                "gist": gist_lines,
            },
        )
        gist_id = getattr(rec2, "id", None)
    except Exception:
        gist_id = None

    try:
        if tr is not None and hasattr(tr, "record_lessons"):
            tr.record_lessons(
                LessonsLearned(
                    trace_id=trace_id,
                    task_id=str(getattr(task, "task_id", "") or ""),
                    content=_safe_str(lesson_content, 1400),
                    tags=["core_loop", f"status:{'success' if done else 'failed'}", domain, environment],
                    meta={
                        "memory_lesson_id": lesson_id,
                        "memory_gist_id": gist_id,
                    },
                )
            )
    except Exception:
        pass

    # Best-effort fast-path backflow via SystemEventQueue
    try:
        queue = getattr(loop, "system_event_queue", None)
        if queue is not None:
            queue.emit_brain_event(
                session_id=str(session_id or "global"),
                event_type="learning.writeback",
                category="learning",
                phase="done",
                source="cognitive_loop",
                payload={
                    "trace_id": trace_id,
                    "task_id": getattr(task, "task_id", ""),
                    "goal_id": getattr(goal, "goal_id", ""),
                    "done": done,
                    "lesson_id": lesson_id,
                    "gist_id": gist_id,
                },
                turn_id=str(getattr(goal, "goal_id", "") or ""),
            )
    except Exception:
        pass

    return lesson_id, gist_id


def write_skill_idea_requests(
    loop: Any,
    *,
    session_id: str,
    trace_id: str,
    goal_id: str,
    domain: str,
    environment: str,
    ideas: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Strong Feedback Point #3b: Reflection skill ideas enqueue.

    Persists the skill idea list into MemoryFabric as a capability acquisition request so
    future planner/executors can see it, and evolution loops can pick it up.
    """
    mf = getattr(loop, "memory_fabric", None)
    if mf is None or not ideas:
        return None

    content = "Skill ideas requested by reflection:\n" + "\n".join(
        f"- {str(i.get('name') or i.get('skill_id') or 'skill')}: {_safe_str(i.get('description') or '', 220)}"
        for i in ideas[:8]
        if isinstance(i, dict)
    )
    rec_id: Optional[str] = None
    try:
        rec = mf.remember_atomic(
            content=content,
            source=f"reflection:skill_ideas:{goal_id}",
            tier=MemoryTier.STS,
            importance=0.75,
            tags=["skill_idea", "reflection", domain, environment, f"session:{session_id}"],
            kind=KIND_CAPABILITY_ACQUISITION_REQUEST,
            domain=domain,
            metadata={
                "trace_id": trace_id,
                "goal_id": goal_id,
                "ideas": ideas[:12],
            },
        )
        rec_id = getattr(rec, "id", None)
    except Exception:
        rec_id = None

    try:
        queue = getattr(loop, "system_event_queue", None)
        if queue is not None:
            queue.emit_brain_event(
                session_id=str(session_id or "global"),
                event_type="learning.skill_ideas",
                category="learning",
                phase="reflection",
                source="cognitive_loop",
                payload={"trace_id": trace_id, "goal_id": goal_id, "count": len(ideas), "memory_id": rec_id},
                turn_id=str(goal_id or ""),
            )
    except Exception:
        pass

    return rec_id
