from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from quentin.cognitive.compaction import compact_session_context

logger = logging.getLogger(__name__)


def _prepare_session_state(loop: Any, *, session_id: str, task: Any) -> Any:
    session_store = getattr(loop, "session_store", None)
    session_policy = getattr(loop, "session_policy", None)
    if session_store is None:
        return None
    state = session_store.load_or_create(str(session_id), metadata={"task_id": str(getattr(task, "task_id", "") or "")})
    state.history.append({"role": "user", "content": str(getattr(task, "input_text", "") or "")})
    state.dirty_flags["history"] = True
    state.touch()
    session_store.save(state)
    session_store.maybe_compact(str(session_id), policy=session_policy)
    return session_store.load_or_create(str(session_id))


async def run_task_async(loop: Any, *, task: Any, cognitive_result_cls: Any) -> Any:
    session_id = (task.metadata or {}).get("session_id") if isinstance(task.metadata, dict) else task.task_id
    from quentin.cognitive.loop_misc import process_output_via_stream_protocol

    from quentin.reflex.classifier import ReflexClassifier
    from quentin.tools.schemas import ToolCallRequest
    from quentin.tools.manager import ToolCallContext
    from quentin.goals.done_definition import DoneCheckResult
    from quentin.cognitive.input_preprocessor import (
        preprocess_input,
        execute_command_async,
        execute_inline_action_async,
    )

    parsed = preprocess_input(
        text=str(task.input_text or ""),
        default_domain=str(getattr(task, "domain", "core") or "core"),
        metadata=dict(getattr(task, "metadata", {}) or {}),
    )
    if isinstance(task.metadata, dict):
        task.metadata.update(parsed.metadata_updates or {})
    if parsed.route_domain:
        task.domain = parsed.route_domain
    task.input_text = parsed.cleaned_text

    command_result = await execute_command_async(loop=loop, task=task, parsed=parsed)
    if command_result is not None:
        final_output, _parsed = process_output_via_stream_protocol(
            loop=loop,
            raw_text=str(command_result.get("final_output") or ""),
            session_id=str(session_id or "global"),
            turn_id=str(task.task_id or ""),
            logger=logger,
            meta={"entrypoint": "command"},
        )
        return cognitive_result_cls(
            task_id=task.task_id,
            goal_id="command",
            final_output=final_output,
            plan_summary=f"Deterministic Command: /{parsed.command_name}",
            actions_summary=str(command_result.get("actions_summary") or ""),
            done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=[f"command /{parsed.command_name} handled deterministically"]),
            done=True,
            done_confidence=1.0,
            self_awareness={"command_hit": True, "command": parsed.command_name},
        )
    inline_action_result = await execute_inline_action_async(loop=loop, task=task, parsed=parsed)
    if isinstance(inline_action_result, dict) and str(inline_action_result.get("status") or "") == "ok":
        final_output, _parsed = process_output_via_stream_protocol(
            loop=loop,
            raw_text=str(inline_action_result.get("final_output") or ""),
            session_id=str(session_id or "global"),
            turn_id=str(task.task_id or ""),
            logger=logger,
            meta={"entrypoint": "inline_action"},
        )
        return cognitive_result_cls(
            task_id=task.task_id,
            goal_id="inline_action",
            final_output=final_output,
            plan_summary="Deterministic Inline Action: /tool",
            actions_summary=str(inline_action_result.get("actions_summary") or ""),
            done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=["inline action handled deterministically"]),
            done=True,
            done_confidence=1.0,
            self_awareness={"inline_action_hit": True, "inline_action": parsed.inline_action},
        )

    reflex = ReflexClassifier()
    action = reflex.classify(task.input_text)

    if action:
        tool_manager = getattr(loop.executor, "tool_manager", None)
        if tool_manager:
            request = ToolCallRequest(tool_name=action.tool_name, payload=action.params)
            context = ToolCallContext(
                metadata={"session_id": task.metadata.get("session_id", "reflex")},
                cancel_token=(task.metadata or {}).get("cancel_token"),
            )
            try:
                result = await tool_manager.call_tool(request, context)
                final_output, _parsed = process_output_via_stream_protocol(
                    loop=loop,
                    raw_text=(str(result.output) if result.success else f"Reflex Error: {result.error}"),
                    session_id=str(session_id or "global"),
                    turn_id=str(task.task_id or ""),
                    logger=logger,
                    meta={"entrypoint": "reflex"},
                )
                return cognitive_result_cls(
                    task_id=task.task_id,
                    goal_id="reflex",
                    final_output=final_output,
                    plan_summary=f"Reflex Action: {action.description}",
                    actions_summary=str(result.output),
                    done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=["Reflex action completed."]),
                    done=True,
                    done_confidence=1.0,
                )
            except Exception:
                pass

    from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator

    session_store = getattr(loop, "session_store", None)
    if session_store is not None:
        try:
            state = _prepare_session_state(loop, session_id=str(session_id), task=task)
            return await lane_orchestrator.run_in_session(
                state,
                lambda: loop._run_goal_internal(task),
                session_store=session_store,
            )
        except Exception:
            logger.debug("run_task_async session model fallback", exc_info=True)

    return await lane_orchestrator.run_in_lane(str(session_id), lambda: loop._run_goal_internal(task))


def run_task(loop: Any, *, task: Any, cognitive_result_cls: Any) -> Any:
    from quentin.cognitive.loop_misc import process_output_via_stream_protocol
    from quentin.reflex.classifier import ReflexClassifier
    from quentin.tools.schemas import ToolCallRequest
    from quentin.tools.manager import ToolCallContext
    from quentin.goals.done_definition import DoneCheckResult
    from quentin.cognitive.input_preprocessor import (
        preprocess_input,
        execute_command_async,
        execute_inline_action_async,
    )

    parsed = preprocess_input(
        text=str(task.input_text or ""),
        default_domain=str(getattr(task, "domain", "core") or "core"),
        metadata=dict(getattr(task, "metadata", {}) or {}),
    )
    if isinstance(task.metadata, dict):
        task.metadata.update(parsed.metadata_updates or {})
    if parsed.route_domain:
        task.domain = parsed.route_domain
    task.input_text = parsed.cleaned_text
    session_id = str((task.metadata or {}).get("session_id") or task.task_id)
    from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
    session_store = getattr(loop, "session_store", None)
    session_state = None
    if session_store is not None:
        try:
            session_state = _prepare_session_state(loop, session_id=session_id, task=task)
        except Exception:
            logger.debug("run_task session model preparation failed", exc_info=True)
            session_state = None

    if parsed.command_name:
        if session_state is not None:
            cmd_out = lane_orchestrator.run_sync_in_session(
                session_state,
                lambda: execute_command_async(loop=loop, task=task, parsed=parsed),
                session_store=session_store,
            )
        else:
            cmd_out = lane_orchestrator.run_sync(
                session_id,
                lambda: execute_command_async(loop=loop, task=task, parsed=parsed),
            )
        if isinstance(cmd_out, dict):
            final_output, _parsed = process_output_via_stream_protocol(
                loop=loop,
                raw_text=str(cmd_out.get("final_output") or ""),
                session_id=str(session_id or "global"),
                turn_id=str(task.task_id or ""),
                logger=logger,
                meta={"entrypoint": "command"},
            )
            return cognitive_result_cls(
                task_id=task.task_id,
                goal_id="command",
                final_output=final_output,
                plan_summary=f"Deterministic Command: /{parsed.command_name}",
                actions_summary=str(cmd_out.get("actions_summary") or ""),
                done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=[f"command /{parsed.command_name} handled deterministically"]),
                done=True,
                done_confidence=1.0,
                self_awareness={"command_hit": True, "command": parsed.command_name},
            )
    if parsed.inline_action:
        if session_state is not None:
            inline_out = lane_orchestrator.run_sync_in_session(
                session_state,
                lambda: execute_inline_action_async(loop=loop, task=task, parsed=parsed),
                session_store=session_store,
            )
        else:
            inline_out = lane_orchestrator.run_sync(
                session_id,
                lambda: execute_inline_action_async(loop=loop, task=task, parsed=parsed),
            )
        if isinstance(inline_out, dict) and str(inline_out.get("status") or "") == "ok":
            final_output, _parsed = process_output_via_stream_protocol(
                loop=loop,
                raw_text=str(inline_out.get("final_output") or ""),
                session_id=str(session_id or "global"),
                turn_id=str(task.task_id or ""),
                logger=logger,
                meta={"entrypoint": "inline_action"},
            )
            return cognitive_result_cls(
                task_id=task.task_id,
                goal_id="inline_action",
                final_output=final_output,
                plan_summary="Deterministic Inline Action: /tool",
                actions_summary=str(inline_out.get("actions_summary") or ""),
                done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=["inline action handled deterministically"]),
                done=True,
                done_confidence=1.0,
                self_awareness={"inline_action_hit": True, "inline_action": parsed.inline_action},
            )

    reflex = ReflexClassifier()
    action = reflex.classify(task.input_text)

    if action:
        executor = getattr(loop, "executor", None)
        tool_manager = getattr(executor, "tool_manager", None) if executor else None
        if tool_manager:
            print(f"⚡ [Reflex] Spinal cord triggered: {action.description}")
            session_id = str((task.metadata or {}).get("session_id") or task.task_id)

            async def _fast_exec() -> Any:
                request = ToolCallRequest(tool_name=action.tool_name, payload=action.params)
                context = ToolCallContext(
                    metadata={"session_id": session_id, "reflex": True},
                    cancel_token=(task.metadata or {}).get("cancel_token"),
                )
                return await tool_manager.call_tool(request, context)

            try:
                if session_state is not None:
                    result = lane_orchestrator.run_sync_in_session(
                        session_state,
                        _fast_exec,
                        session_store=session_store,
                    )
                else:
                    result = lane_orchestrator.run_sync(session_id, _fast_exec)
                output_text = str(result.output.get("result") or result.output)
                final_output, _parsed = process_output_via_stream_protocol(
                    loop=loop,
                    raw_text=output_text,
                    session_id=str(session_id or "global"),
                    turn_id=str(task.task_id or ""),
                    logger=logger,
                    meta={"entrypoint": "reflex"},
                )
                return cognitive_result_cls(
                    task_id=task.task_id,
                    goal_id="reflex",
                    final_output=final_output,
                    plan_summary=f"Spinal Reflex: {action.tool_name}",
                    actions_summary=action.description,
                    done_result=DoneCheckResult(is_done=True, confidence=1.0, reasons=["Executed via spinal reflex"]),
                    done=True,
                    done_confidence=1.0,
                    self_awareness={"reflex_hit": True},
                )
            except Exception as err:
                logger.warning("CognitiveLoop: Reflex failed, falling back to full brain: %s", err)

    if session_state is not None:
        return lane_orchestrator.run_sync_in_session(
            session_state,
            lambda: loop._run_goal_internal(task),
            session_store=session_store,
        )
    return loop.run_goal(task)


async def collect_runtime_perception(*, task: Any) -> Dict[str, Any]:
    perception_data: Dict[str, Any] = {}
    try:
        from quentin.cognitive.vision_budget import allocate_vision_token_budget

        perception_data["vision_budget"] = allocate_vision_token_budget(
            domain=str(getattr(task, "domain", "") or ""),
            metadata=dict(getattr(task, "metadata", {}) or {}),
        )
        try:
            md = dict(getattr(task, "metadata", {}) or {})
            md["vision_budget"] = dict(perception_data.get("vision_budget") or {})
            task.metadata = md
        except Exception:
            pass
    except Exception:
        pass
    domain = str(task.domain).lower()
    if domain == "mobile":
        from quentin.infra.mobile.adb_client import adb_client
        from quentin.infra.mobile.tree_optimizer import tree_optimizer

        perception_data["screenshot"] = adb_client.get_screenshot()
        perception_data["ui_tree"] = tree_optimizer.optimize_xml(adb_client.dump_hierarchy())
    elif domain == "web":
        from quentin.infra.browser.manager import browser_manager

        perception_data["screenshot"] = (await browser_manager.get_labeled_screenshot())[0]
        perception_data["ui_tree"] = await browser_manager.get_pruned_ui_tree()
    elif domain == "desktop":
        from quentin.infra.desktop.manager import desktop_manager

        perception_data["screenshot"] = await desktop_manager.get_screenshot()
        perception_data["ui_tree"] = await desktop_manager.get_ui_tree()
    return perception_data


def try_reflex_plan_from_perception(
    loop: Any,
    *,
    planner_result_cls: Any,
    task: Any,
    goal: Any,
    effective_ctx: Dict[str, Any],
    perception_snapshot: Optional[Any],
    trace_id: str,
    attempt_index: int,
) -> Optional[Any]:
    if not (
        perception_snapshot is not None
        and getattr(loop.perception_layer, "config", None) is not None
        and bool(getattr(loop.perception_layer.config, "enable_situation_to_skill", False))
        and getattr(loop.perception_layer, "situation_skill_router", None) is not None
        and str(task.domain or "").strip().lower() not in {"legal", "trading"}
    ):
        return None
    try:
        invocation = loop.perception_layer.situation_skill_router.route(situation=perception_snapshot.situation, ctx=effective_ctx)
    except Exception:
        invocation = None
    if invocation is None:
        return None

    reflex_steps = [
        {
            "step_id": "s_reflex_1",
            "description": f"[reflex] run skill {invocation.skill_id}",
            "skill_id": invocation.skill_id,
            "notes": invocation.reason,
        }
    ]
    result = planner_result_cls(
        goal_id=goal.goal_id,
        raw_output=json.dumps(
            {
                "steps": reflex_steps,
                "reflex": invocation.to_dict(),
                "perception": perception_snapshot.to_dict(),
            },
            ensure_ascii=False,
        ),
        steps=reflex_steps,
        used_skills=[],
    )
    try:
        from quentin.traces.core import TraceEventType, new_trace_event

        loop.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.DECISION,
                payload={
                    "action": "situation_to_skill_hit",
                    "attempt_index": attempt_index,
                    "goal_id": goal.goal_id,
                    "invocation": invocation.to_dict(),
                },
            )
        )
    except Exception:
        pass
    return result


async def check_context_and_flush(loop: Any, *, goal: Any, metrics: Dict[str, Any], session_id: str) -> None:
    from quentin.llm.context_budget import get_context_window_limit

    limit = get_context_window_limit()
    current = metrics.get("cost_tokens", 0)
    if current > (limit * 0.8):
        print(f"🚨 [ContextGuard] Near overflow ({current}/{limit}). Triggering proactive compaction...")
        result = await compact_session_context(
            session_id=session_id,
            memory_fabric=loop.memory_fabric,
            model_router=loop.model_router,
        )
        if result.get("compacted"):
            print("✅ [ContextGuard] Proactive compaction successful.")
            logger.info("CognitiveLoop: Proactive compaction for session %s succeeded.", session_id)
