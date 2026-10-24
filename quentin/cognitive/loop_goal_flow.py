from __future__ import annotations

import json
import logging
import uuid
import os
from typing import Any, Dict, List, Optional

from quentin.cognitive.self_awareness import SelfAwarenessEngine
from quentin.cognitive.loop_orchestration import LoopRuntimeState
from quentin.cognitive.attempt_budget import (
    initialize_attempt_budget,
    consume_attempt_budget,
)
from quentin.utils.time import now_utc_iso
from quentin.agents.pi_embedded_helpers.bootstrap import build_bootstrap_context

logger = logging.getLogger(__name__)


def _emit_loop_event(
    loop: Any,
    *,
    session_id: str,
    turn_id: str,
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
            turn_id=str(turn_id or ""),
        )
    except Exception:
        pass


async def run_goal_internal(loop: Any, *, task: Any) -> Any:
    """
    Main goal loop: Planner -> Executor -> Done -> Reflection -> ImmuneLoop.

    Implemented as a helper to keep loop_impl.py small; uses `loop` for dependencies.
    """
    session_id = str((task.metadata or {}).get("session_id") or task.task_id or "global")
    from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
    from quentin.infra.tools.state_manager import PhysicalStateManager
    from quentin.infra.llm.parameter_scaler import ParameterScaler

    await lane_orchestrator.acquire(lane_id=session_id, task_id=task.task_id)
    try:
        start_ts = now_utc_iso()
        trace_id = f"trace_{uuid.uuid4().hex}"
        turn_id = str(task.task_id or "")
        _emit_loop_event(
            loop,
            session_id=session_id,
            turn_id=turn_id,
            event_type="turn_start",
            category="turn",
            phase="start",
            payload={"task_id": str(task.task_id or ""), "domain": str(task.domain or "core"), "environment": str(task.environment or "sandbox")},
        )
        try:
            meta = task.metadata if isinstance(task.metadata, dict) else {}
            meta["bootstrap_context"] = build_bootstrap_context().to_dict()
            task.metadata = meta
        except Exception:
            pass
        run_ctx = await loop._prepare_run_context(task=task, trace_id=trace_id)
        if run_ctx.early_result is not None:
            _emit_loop_event(
                loop,
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn_end",
                category="turn",
                phase="end",
                payload={"status": "early_result"},
            )
            return run_ctx.early_result

        metrics = {
            "total_attempts": 0,
            "success_attempts": 0,
            "error_attempts": 0,
            "cost_tokens": 0.0,
            "latency_ms": 0.0,
            "tool_call_count": 0,
            "prediction_error_count": 0,
            "prediction_error_rate": 0.0,
            "retry_budget_initial": 0.0,
            "retry_budget_remaining": 0.0,
            "last_retry_cost": 0.0,
        }
        self_awareness_engine = SelfAwarenessEngine()
        state = LoopRuntimeState(
            current_think_level=str(task.metadata.get("think_level", "off")),
            latest_self_awareness=self_awareness_engine.current_snapshot(),
        )

        max_loops = max(1, int(os.getenv("QUENTIN_MAX_LOOPS", "5") or "5"))
        budget_state = initialize_attempt_budget(max_loops=max_loops)
        metrics["retry_budget_initial"] = budget_state.initial_budget
        metrics["retry_budget_remaining"] = budget_state.remaining_budget
        loop_idx = 0
        state_mgr = None
        enable_physical_snapshot = str(
            os.getenv("QUENTIN_ENABLE_PHYSICAL_SNAPSHOT", "0") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if enable_physical_snapshot:
            state_mgr = PhysicalStateManager(loop.repo_root)
            state_mgr.capture_snapshot(label=f"task_{task.task_id[:8]}")

        while loop_idx < max_loops:
            if float(metrics.get("retry_budget_remaining", 0.0) or 0.0) <= 0.0:
                logger.warning("CognitiveLoop: retry budget exhausted, stopping loop early.")
                break
            loop_idx += 1
            metrics["total_attempts"] += 1
            _emit_loop_event(
                loop,
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn_attempt_start",
                category="turn",
                phase="start",
                payload={
                    "attempt_index": int(metrics["total_attempts"] or loop_idx),
                    "retry_budget_remaining": float(metrics.get("retry_budget_remaining", 0.0) or 0.0),
                },
            )

            last_error = str(state.last_exec_result.get("error", "")) if state.last_exec_result else None
            task.metadata["llm_params"] = ParameterScaler.scale(
                base_params={"temperature": 0.0, "top_p": 0.9},
                failure_count=metrics["error_attempts"],
                last_error=last_error,
                token_usage=float(metrics.get("cost_tokens", 0.0) or 0.0),
                model_name=str((task.metadata or {}).get("llm_model") or ""),
                provider_name=str((task.metadata or {}).get("llm_provider") or ""),
            )

            cwd = os.getcwd()
            current_input = getattr(task, "input_text", "")
            if f"[Working directory:" not in current_input:
                task.input_text = f"[Working directory: {cwd}]\n\n{current_input}"

            # P5: Surgery One Hundred and Three - Context Pruning (OpenClaw Parity)
            from quentin.cognitive.context_pruning import ContextPruner
            pruner = ContextPruner()
            task.history = pruner.prune(getattr(task, "history", []))

            # P5: Surgery Fifty-four - Session Compaction (OpenClaw Parity)
            from quentin.cognitive.session_compactor import SessionCompactor
            compactor = SessionCompactor(model_router=loop.model_router)
            
            # Estimate tokens (4 chars per token)
            est_tokens = len(str(task.history)) // 4
            max_ctx = int(os.getenv("LLM_MAX_CONTEXT_TOKENS", "128000"))
            
            new_history, was_compacted = await compactor.compact_if_needed(
                messages=task.history,
                max_tokens=max_ctx,
                current_tokens=est_tokens
            )
            if was_compacted:
                task.history = new_history
                _emit_loop_event(
                    loop,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="compaction_end",
                    category="compaction",
                    phase="end",
                    payload={"mode": "session_compactor", "status": "compacted", "attempt_index": int(metrics["total_attempts"] or loop_idx)},
                )

            # P5: Surgery One Hundred and Nine - Role Ordering Guard (OpenClaw Parity)
            # Ensure protocol compliance (User -> Assistant -> User)
            if task.history and task.history[-1].get("role") == "user":
                logger.warning("CognitiveLoop: Consecutive User messages detected. Injecting sync filler.")
                task.history.append({
                    "role": "assistant",
                    "content": "I acknowledge your last instruction. Processing now..."
                })
                _emit_loop_event(
                    loop,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="message",
                    category="message",
                    phase="update",
                    payload={"kind": "sync_filler", "attempt_index": int(metrics["total_attempts"] or loop_idx)},
                )

            step_result = await loop._run_single_attempt(
                task=task,
                run_ctx=run_ctx,
                trace_id=trace_id,
                loop_idx=loop_idx,
                metrics=metrics,
                state=state,
                self_awareness_engine=self_awareness_engine,
            )

            if state.last_exec_result and not state.last_exec_result.get("success"):
                err = str(state.last_exec_result.get("error", "")).lower()
                if state_mgr is not None and ("physical_assertion_failed" in err or "syntax error" in err):
                    logger.warning("CognitiveLoop: Physical failure detected. TRIGGERING ROLLBACK.")
                    state_mgr.rollback()
                    state_mgr.capture_snapshot(label=f"retry_{loop_idx}")

            if step_result == "retry":
                _emit_loop_event(
                    loop,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="turn_attempt_end",
                    category="turn",
                    phase="end",
                    payload={"attempt_index": int(metrics["total_attempts"] or loop_idx), "status": "retry"},
                )
                loop_idx -= 1
                continue
            attempt_eval = metrics.get("last_attempt_evaluation")
            if not isinstance(attempt_eval, dict):
                attempt_eval = {}
            budget_state, consumed = consume_attempt_budget(
                state=budget_state,
                attempt_evaluation=attempt_eval,
                step_result=step_result,
            )
            metrics["retry_budget_remaining"] = budget_state.remaining_budget
            metrics["last_retry_cost"] = consumed
            if isinstance(task.metadata, dict):
                task.metadata["retry_budget_remaining"] = float(budget_state.remaining_budget)
                task.metadata["last_retry_cost"] = float(consumed)
            if step_result == "break":
                _emit_loop_event(
                    loop,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="turn_attempt_end",
                    category="turn",
                    phase="end",
                    payload={"attempt_index": int(metrics["total_attempts"] or loop_idx), "status": "break"},
                )
                break
            _emit_loop_event(
                loop,
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn_attempt_end",
                category="turn",
                phase="end",
                payload={"attempt_index": int(metrics["total_attempts"] or loop_idx), "status": "continue"},
            )

        if state.done_result and state.done_result.is_done:
            state_mgr.commit_success()

        result = loop._finalize_goal_result(
            start_ts=start_ts,
            trace_id=trace_id,
            task=task,
            goal=run_ctx.goal,
            last_plan_result=state.last_plan_result,
            actions_summary=state.actions_summary,
            final_output=state.final_output,
            done_result=state.done_result,
            metrics=metrics,
            last_exec_result=state.last_exec_result,
            latest_self_awareness=state.latest_self_awareness,
            idempotency=run_ctx.idempotency,
            executor=run_ctx.executor,
        )
        _emit_loop_event(
            loop,
            session_id=session_id,
            turn_id=turn_id,
            event_type="message",
            category="message",
            phase="end",
            payload={
                "kind": "final_output",
                "done": bool(getattr(result, "done", False)),
                "final_output_preview": str(getattr(result, "final_output", "") or "")[:1200],
            },
        )
        _emit_loop_event(
            loop,
            session_id=session_id,
            turn_id=turn_id,
            event_type="turn_end",
            category="turn",
            phase="end",
            payload={"status": "completed", "done": bool(getattr(result, "done", False)), "attempts": int(metrics.get("total_attempts") or 0)},
        )
        return result
    finally:
        lane_orchestrator.release(lane_id=session_id, task_id=task.task_id)


def run_planner_or_custom(
    loop: Any,
    *,
    planner_result_cls: Any,
    task: Any,
    goal: Any,
    extra_ctx: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Prefer a custom planner if provided; fallback to the council-based planner.

    This enables offline/unit-test execution without requiring a live LLM provider.
    """
    try:
        proc_ctx = procedural_memory_context(loop, task=task, goal=goal)
    except Exception:
        proc_ctx = {}

    try:
        lesson_ctx = lesson_memory_context(loop, task=task, goal=goal)
    except Exception:
        lesson_ctx = {}

    try:
        gist_ctx = gist_memory_context(loop, task=task, goal=goal)
    except Exception:
        gist_ctx = {}

    combined_ctx = {**proc_ctx, **lesson_ctx, **gist_ctx, **(extra_ctx or {})}

    if loop._planner is None:
        safe_task = task.to_goal_spec()
        return loop._run_planner(goal, context={"task": safe_task, **combined_ctx})

    try:
        context = {"task": task.to_goal_spec(), **proc_ctx}
        if hasattr(loop._planner, "plan") and callable(getattr(loop._planner, "plan")):
            out = loop._planner.plan(goal.description or goal.title or "", context)  # type: ignore[call-arg]
        else:
            out = loop._planner(task, goal)  # type: ignore[misc]
    except TypeError:
        out = loop._planner(  # type: ignore[misc]
            goal.description or goal.title or "",
            {"task": task.to_goal_spec(), **proc_ctx},
        )

    if isinstance(out, planner_result_cls):
        return out
    if isinstance(out, dict):
        steps = out.get("steps") or []
        if not isinstance(steps, list):
            steps = []
        return planner_result_cls(
            goal_id=goal.goal_id,
            raw_output=json.dumps(out, ensure_ascii=False),
            steps=steps,
            used_skills=[],
        )
    return planner_result_cls(
        goal_id=goal.goal_id,
        raw_output=str(out),
        steps=[{"step_id": "s1", "description": str(out), "skill_id": None, "notes": "custom_planner"}],
        used_skills=[],
    )


def procedural_memory_context(loop: Any, *, task: Any, goal: Any) -> Dict[str, Any]:
    """
    Minimal procedural memory injection (SleepLoop output) into planner context.
    """
    try:
        from quentin.memory.models import MemoryQuery
    except Exception:
        return {}

    query_text = (goal.title or goal.description or task.input_text or "").strip()
    if not query_text:
        return {}

    recs = loop.memory_fabric.recall(
        MemoryQuery(
            text=query_text,
            kind="procedural",
            top_k=3,
        )
    )
    items: List[Dict[str, Any]] = []
    for r in recs:
        items.append(
            {
                "id": getattr(r, "id", ""),
                "tier": getattr(getattr(r, "tier", None), "value", None),
                "domain": getattr(r, "domain", None),
                "content": (getattr(r, "content", "") or "")[:2000],
                "tags": list(getattr(r, "tags", []) or [])[:32],
            }
        )
    return {"procedural_memories": items}


def lesson_memory_context(loop: Any, *, task: Any, goal: Any) -> Dict[str, Any]:
    """
    Inject a small number of recent/related 'lesson' memories into planner context.
    """
    try:
        from quentin.memory.models import MemoryQuery
        from quentin.memory.kinds import KIND_LESSON
    except Exception:
        return {}

    query_text = (goal.title or goal.description or task.input_text or "").strip()
    if not query_text:
        return {}

    top_k = 3
    try:
        top_k = int(getattr(loop.cognitive_policies, "lesson_top_k", 3) or 3)
    except Exception:
        top_k = 3
    if top_k <= 0:
        return {}

    try:
        recs = loop.memory_fabric.recall(MemoryQuery(text=query_text, kind=KIND_LESSON, top_k=top_k))
    except Exception:
        return {}

    items: List[Dict[str, Any]] = []
    for r in recs or []:
        items.append(
            {
                "id": getattr(r, "id", ""),
                "tier": getattr(getattr(r, "tier", None), "value", None),
                "domain": getattr(r, "domain", None),
                "content": (getattr(r, "content", "") or "")[:1200],
                "tags": list(getattr(r, "tags", []) or [])[:32],
                "metadata": dict(getattr(r, "metadata", None) or {}),
            }
        )
    return {"lesson_memories": items}


def gist_memory_context(loop: Any, *, task: Any, goal: Any) -> Dict[str, Any]:
    """
    Inject a small number of gist memories into planner context.
    """
    if not bool(getattr(loop.cognitive_policies, "enable_gist_injection", True)):
        return {}
    try:
        from quentin.memory.models import MemoryQuery
        from quentin.memory.kinds import KIND_GIST_MEMORY
    except Exception:
        return {}

    query_text = (goal.title or goal.description or task.input_text or "").strip()
    if not query_text:
        return {}
    top_k = int(getattr(loop.cognitive_policies, "gist_top_k", 3) or 0)
    if top_k <= 0:
        return {}

    try:
        recs = loop.memory_fabric.recall(MemoryQuery(text=query_text, kind=KIND_GIST_MEMORY, top_k=top_k))
    except Exception:
        return {}

    items: List[Dict[str, Any]] = []
    for r in recs or []:
        md = getattr(r, "metadata", None) or {}
        gist = md.get("gist") if isinstance(md, dict) else None
        if isinstance(gist, list) and gist:
            snippet = "\n".join([f"- {str(x)}" for x in gist[:10]])
        else:
            snippet = str(getattr(r, "content", "") or "")[:1500]
        items.append(
            {
                "id": getattr(r, "id", ""),
                "tier": getattr(getattr(r, "tier", None), "value", None),
                "domain": getattr(r, "domain", None),
                "gist": snippet,
                "tags": list(getattr(r, "tags", []) or [])[:32],
            }
        )
    return {"gist_memories": items}


async def summarize_history(loop: Any, *, memories: List[Any], goal_id: str) -> str:
    """
    Condense historical logs into a few concise lessons to avoid context bloat.
    """
    if not memories:
        return ""

    raw_text = "\n".join([str(m.content) for m in memories])
    if len(raw_text) < 500:
        return raw_text

    from quentin.llm.client import call_llm

    cfg = loop.model_router.route(mode="planner", task_type="core")

    prompt = (
        f"Review the following past execution attempts for Goal {goal_id}.\n"
        f"Identify the CORE REASON for previous failures and provide 2-3 ACTIONABLE LESSONS.\n"
        f"Keep it extremely concise (max 150 words).\n\n"
        f"PAST ATTEMPTS:\n{raw_text}"
    )

    try:
        summary = call_llm(
            cfg,
            user_prompt=prompt,
            system_prompt="You are a senior system debugger. Summarize failures into concise lessons.",
            actor="debugger",
            domain="core",
        )
        return summary
    except Exception as e:
        logger.debug("Summarize history failed: %s", e)
        return raw_text[:2000]
