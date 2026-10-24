from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from quentin.cognitive.context_snapshots import bootstrap_snapshots, is_context_snapshots_enabled
from quentin.traces.core import TraceEventType, new_trace_event

import logging

logger = logging.getLogger(__name__)


def get_environment_snapshot(
    loop: Any,
    *,
    focus_paths: Optional[List[str]] = None,
    focused_only: bool = False,
    max_lines: int = 300,
    task: Optional[Any] = None,
) -> str:
    """Generate environment snapshot for planner context construction."""
    if is_context_snapshots_enabled():
        registry = bootstrap_snapshots()
        ctx_data = {"task_input": task.input_text if task else ""}
        blocks = registry.collect_all(repo_root=loop.repo_root, context=ctx_data)

        if blocks:
            lines = ["ENVIRONMENT SNAPSHOT (V2 STRUCTURED):"]
            for b in blocks:
                lines.append(f"### {b.title} ({b.id})")
                lines.append(b.content)
                lines.append("-" * 20)
            return "\n".join(lines)

    heartbeat_guide = ""
    try:
        hb_path = loop.repo_root / "quentin" / "mutable" / "HEARTBEAT.md"
        if hb_path.exists():
            heartbeat_guide = f"\n\nSYSTEM HEARTBEAT GUIDE (User-Editable):\n{hb_path.read_text(encoding='utf-8')[:2000]}"
    except Exception:
        pass

    try:
        ignore_dirs = {".git", "__pycache__", "venv", ".venv", ".pytest_cache", ".gemini", "node_modules", "data", "logs", "ai", "docs"}
        tree: List[str] = []
        root_dir = loop.repo_root

        def _append_subtree(base: Path, *, depth_limit: int, file_limit: int, title: Optional[str] = None) -> None:
            if not base.exists():
                return
            if title:
                tree.append(title)
            for root, dirs, files in os.walk(str(base)):
                dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
                rel_path = os.path.relpath(root, str(base))
                depth = 0 if rel_path == "." else rel_path.count(os.sep) + 1
                if depth > depth_limit:
                    continue
                current = Path(root)
                rel_display = str(current.relative_to(loop.repo_root)) if current != loop.repo_root else "."
                indent = " " * 2 * depth
                tree.append(f"{indent}{rel_display}/")
                sub_indent = " " * 2 * (depth + 1)
                visible_files = [f for f in sorted(files) if not f.startswith(".")]
                for f in visible_files[:file_limit]:
                    tree.append(f"{sub_indent}{f}")
                if len(visible_files) > file_limit:
                    tree.append(f"{sub_indent}...")

        if focus_paths:
            try:
                focus_depth = int(os.getenv("QUENTIN_PRE_SENSING_FOCUS_DEPTH", "4") or "4")
            except Exception:
                focus_depth = 4
            try:
                focus_file_limit = int(os.getenv("QUENTIN_PRE_SENSING_FOCUS_FILES_PER_DIR", "30") or "30")
            except Exception:
                focus_file_limit = 30
            tree.append("Focused Paths:")
            for raw in focus_paths:
                rel = str(raw or "").strip().strip("/")
                if not rel:
                    continue
                base = (loop.repo_root / rel).resolve()
                try:
                    base.relative_to(loop.repo_root)
                except Exception:
                    continue
                _append_subtree(base, depth_limit=focus_depth, file_limit=focus_file_limit)

        if not focused_only:
            try:
                base_items = os.listdir(str(root_dir))
                tree.append("Project Root Structure:")
                for item in sorted(base_items):
                    if item in ignore_dirs or item.startswith("."):
                        continue
                    full = root_dir / item
                    tree.append(f"  {item}/" if full.is_dir() else f"  {item}")
            except Exception:
                pass
            _append_subtree(root_dir, depth_limit=3, file_limit=10, title="\nDetailed Tree (partial):")

        limit = max(50, int(max_lines or 300))
        return "\n".join(tree[:limit]) + heartbeat_guide
    except Exception as e:
        return f"Error gathering snapshot: {e}" + heartbeat_guide


def compute_plan_for_attempt(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    session_id: str,
    trace_id: str,
    attempt_index: int,
    historical_context: str,
    last_plan_result: Optional[Any],
    last_exec_result: Dict[str, Any],
    latest_self_awareness: Any,
    perception_data: Dict[str, Any],
    critical_instruction: str = "",
    failure_count: int = 0,
    tool_only_no_update_count: int = 0,
    retry_budget_remaining: float = 0.0,
    interrupt_cooldown_remaining: int = 0,
) -> Tuple[Any, Dict[str, Any], str]:
    env_snapshot, focus_paths_for_planner = loop._refresh_planner_environment_snapshot(
        task=task,
        last_exec_result=last_exec_result,
    )

    # Even if reflection provides a plan override, we still want to propagate
    # last-attempt diagnostics into traces (OpenClaw parity for attempt.ts signals).
    event_hint = loop._drain_system_events_for_planner(session_id=session_id)
    forbidden_actions = loop._recent_forbidden_actions(limit=6)
    if forbidden_actions:
        task.metadata["forbidden_actions"] = forbidden_actions

    plan_override = loop._get_plan_override_if_any(goal)
    if plan_override:
        logger.info("CognitiveLoop: Using plan override from reflection")
        plan_result = loop._build_planner_result_from_reflection(goal, plan_override)
        if hasattr(loop, "_planner_overrides"):
            loop._planner_overrides.pop(getattr(goal, "goal_id"), None)

        last_eval: Dict[str, Any] = {}
        if isinstance(last_exec_result, dict) and isinstance(last_exec_result.get("attempt_evaluation"), dict):
            last_eval = dict(last_exec_result.get("attempt_evaluation") or {})
        elif isinstance(task.metadata, dict) and isinstance(task.metadata.get("last_attempt_evaluation"), dict):
            last_eval = dict(task.metadata.get("last_attempt_evaluation") or {})

        override_ctx = {
            "override": True,
            "last_attempt_evaluation": last_eval,
            "planner_lifecycle_payload": {"stage": "override", "attempt_index": int(attempt_index or 0)},
            "planning_strategy_patch": {},
            "planner_payload_variant": {},
            "retry_plan_delta": {},
            "candidate_files": loop._get_candidate_files(task.input_text),
            "system_event_prompt": event_hint,
            "forbidden_actions": forbidden_actions,
        }
        return plan_result, override_ctx, env_snapshot
    planner_ctx = loop._build_base_planner_context(
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
    perception_snapshot = None
    effective_ctx = loop._build_effective_planner_context(task=task, planner_ctx=planner_ctx)

    if loop.perception_layer is not None:
        try:
            perception_snapshot = loop.perception_layer.build_snapshot(ctx=effective_ctx)
            if (
                perception_snapshot.situation.situation_id == "unknown_text_only"
                or perception_snapshot.situation.confidence < 0.3
            ):
                perception_snapshot.situation.situation_id = "exploratory_task"
                perception_snapshot.situation.confidence = max(perception_snapshot.situation.confidence, 0.45)
            loop._update_task_from_perception_snapshot(task=task, perception_snapshot=perception_snapshot)
            try:
                loop.trace_recorder.record_event(
                    new_trace_event(
                        trace_id=trace_id,
                        event_type=TraceEventType.DECISION,
                        payload={
                            "action": "perception_snapshot",
                            "attempt_index": attempt_index,
                            "goal_id": goal.goal_id,
                            "snapshot": perception_snapshot.to_dict(),
                        },
                    )
                )
            except Exception:
                pass
        except Exception:
            perception_snapshot = None

    plan_result = loop._try_reflex_plan_from_perception(
        task=task,
        goal=goal,
        effective_ctx=effective_ctx,
        perception_snapshot=perception_snapshot,
        trace_id=trace_id,
        attempt_index=attempt_index,
    )
    planner_ctx = loop._apply_attention_context(
        planner_ctx=planner_ctx,
        perception_snapshot=perception_snapshot,
    )
    if plan_result is None:
        print("📝 [Planning] Councils are debating the best strategy...")
        plan_result = loop._run_planner_or_custom(task, goal, extra_ctx=planner_ctx)
    return plan_result, planner_ctx, env_snapshot
