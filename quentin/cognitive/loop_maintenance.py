from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.council.done import DoneCouncil
from quentin.council.manager import CouncilManager, CouncilQuestion
from quentin.council.reflection import ReflectionCouncil
from quentin.execution.skill_executor import Executor as SkillExecutor
from quentin.goals.done_definition import GoalDoneManager
from quentin.immune.loop import ImmuneLoop
from quentin.kernel.safety import SafetyKernel
from quentin.l3.research.interface import ResearchInterface
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.session_deltas import SessionDeltaConfig, SessionDeltaWriter
from quentin.models.router import ModelRouter
from quentin.skills.manager import SkillManager
from quentin.tools.manager import ToolManager
from quentin.traces.execution_trace import ExecutionTrace, ExecutionTraceStore
from quentin.traces.core import JsonlTraceRecorder
from quentin.runtime.system_events import SystemEventQueue
from quentin.cognitive.contract import RequirementContractor
from quentin.config.cognitive_policies import load_cognitive_policies
from quentin.utils.time import now_utc_iso
from quentin.infra.sessions.dirty_sync import dirty_sync, build_memory_sync_callback
from quentin.infra.sessions.session_store import SessionPolicy, SessionStore
from quentin.memory.manager import MemoryManager, MemoryManagerConfig

logger = logging.getLogger(__name__)


def initialize_loop(
    loop: Any,
    *,
    repo_root: str | Path = ".",
    planner: Optional[Any] = None,
    executor: Optional[Any] = None,
    perception_layer: Optional[Any] = None,
    cognitive_policies: Optional[Any] = None,
    goal_manager: Optional[GoalDoneManager] = None,
    memory_fabric: Optional[MemoryFabric] = None,
    traces_store: Optional[ExecutionTraceStore] = None,
    skill_manager: Optional[SkillManager] = None,
    model_router: Optional[ModelRouter] = None,
    done_council: Optional[DoneCouncil] = None,
    reflection_council: Optional[ReflectionCouncil] = None,
    immune_loop: Optional[ImmuneLoop] = None,
    safety_kernel: Optional[SafetyKernel] = None,
    session_delta_config: Optional[SessionDeltaConfig] = None,
    system_event_queue: Optional[SystemEventQueue] = None,
    council_manager: Optional[CouncilManager] = None,
    tool_manager: Optional[ToolManager] = None,
    self_programming_engine: Optional[Any] = None,
) -> None:
    loop.repo_root = Path(repo_root).resolve()
    loop.model_router = model_router or ModelRouter()
    loop.cognitive_policies = cognitive_policies or load_cognitive_policies(repo_root=loop.repo_root)
    loop.goal_manager = goal_manager or GoalDoneManager(repo_root=loop.repo_root)
    try:
        loop.memory_fabric = memory_fabric or MemoryFabric(repo_root=loop.repo_root)
    except TypeError:
        loop.memory_fabric = memory_fabric or MemoryFabric()
    loop.memory_manager = MemoryManager(
        memory_fabric=loop.memory_fabric,
        repo_root=loop.repo_root,
        config=MemoryManagerConfig(
            periodic_sync_enabled=(os.getenv("QUENTIN_MEMORY_PERIODIC_SYNC", "0").strip().lower() in ("1", "true", "yes", "on")),
            periodic_sync_interval_s=float(os.getenv("QUENTIN_MEMORY_PERIODIC_SYNC_INTERVAL_S", "60") or 60.0),
            memory_sync_concurrency=int(os.getenv("QUENTIN_MEMORY_SYNC_CONCURRENCY", "0") or 0),
        ),
    )
    try:
        loop.memory_fabric.set_pre_search_sync_hook(loop.memory_manager.maybe_sync_before_search)
    except Exception:
        pass
    loop.memory_manager.start_periodic_sync()
    loop.session_store = SessionStore(repo_root=loop.repo_root)
    loop.session_policy = SessionPolicy()
    # Bind dirty session sync to transcript incremental memory indexing.
    dirty_sync.sync_callback = build_memory_sync_callback(
        memory_fabric=loop.memory_fabric,
        repo_root=loop.repo_root,
    )
    # Unified runtime tuning for dirty sync behavior.
    try:
        rc = getattr(loop.memory_fabric, "runtime_config", None)
        if rc is not None:
            dirty_sync.configure(
                debounce_sec=float(getattr(rc, "dirty_debounce_sec", dirty_sync.debounce_sec)),
                dedupe_ttl_sec=float(getattr(rc, "dirty_dedupe_ttl_sec", dirty_sync.dedupe_ttl_sec)),
            )
    except Exception:
        pass
    loop.traces_store = traces_store or ExecutionTraceStore(repo_root=loop.repo_root)
    loop.trace_recorder = JsonlTraceRecorder(repo_root=str(loop.repo_root))
    loop.skill_manager = skill_manager or SkillManager(repo_root=loop.repo_root)
    loop.tool_manager = tool_manager or getattr(executor, "tool_manager", None) or ToolManager()
    loop.safety_kernel = safety_kernel or SafetyKernel()
    try:
        from quentin.tools.usage.tool_knowledge_sink import ToolKnowledgeUsageSink

        sinks = list(getattr(loop.tool_manager, "_usage_sinks", []) or [])
        if not any(isinstance(s, ToolKnowledgeUsageSink) for s in sinks):
            loop.tool_manager.add_usage_sink(ToolKnowledgeUsageSink(memory_fabric=loop.memory_fabric))
    except Exception:
        pass
    loop.session_delta_writer = SessionDeltaWriter(
        memory_fabric=loop.memory_fabric,
        safety_kernel=loop.safety_kernel,
        config=session_delta_config,
        session_store=loop.session_store,
    )
    loop.system_event_queue = system_event_queue or SystemEventQueue(repo_root=loop.repo_root)
    loop.perception_layer = perception_layer
    loop.contractor = RequirementContractor(loop.repo_root)

    loop.council_manager = council_manager or CouncilManager(
        repo_root=loop.repo_root,
        model_router=loop.model_router,
    )
    loop.done_council = done_council or DoneCouncil(council_manager=loop.council_manager)
    loop.reflection_council = reflection_council or ReflectionCouncil(council_manager=loop.council_manager)
    loop.executor = executor or SkillExecutor(
        repo_root=loop.repo_root,
        model_router=loop.model_router,
        skill_manager=loop.skill_manager,
        tool_manager=loop.tool_manager,
    )
    if getattr(loop.executor, "tool_manager", None) is None:
        try:
            loop.executor.tool_manager = loop.tool_manager
        except Exception:
            pass
    elif getattr(loop.executor, "tool_manager", None) is not loop.tool_manager:
        loop.tool_manager = loop.executor.tool_manager
    try:
        if hasattr(loop.tool_manager, "set_event_queue"):
            loop.tool_manager.set_event_queue(loop.system_event_queue)
    except Exception:
        pass

    try:
        research_interface = ResearchInterface()
    except Exception:
        logger.exception("CognitiveLoop: failed to init ResearchInterface, continuing without it")
        research_interface = None
    loop.immune_loop = immune_loop or ImmuneLoop(
        repo_root=loop.repo_root,
        research_interface=research_interface,
    )

    from quentin.tools.subagents import create_subagent_pack
    from quentin.tools.schemas import ToolSpec

    subagent_tools = create_subagent_pack(loop)
    for t in subagent_tools:
        spec = ToolSpec(
            name=t["name"],
            description=t["description"],
            input_schema=t["input_schema"],
        )
        loop.tool_manager.register_tool(spec, t["handler"])
        logger.info("CognitiveLoop: Registered dynamic subagent tool: %s", t["name"])

    loop.degrade_mode = False
    loop.self_programming_enabled = True
    loop.self_programming_engine = self_programming_engine
    try:
        from quentin.cognitive.self_programming_hook import SelfProgrammingHook

        loop.self_programming_hook = SelfProgrammingHook(loop=loop)
    except Exception:
        loop.self_programming_hook = None
    loop._planner = planner
    loop._executor = executor


def write_trace(
    loop: Any,
    *,
    trace_id: str,
    task: Any,
    goal: Any,
    done_result: Optional[Any],
    start_ts: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        trace = ExecutionTrace(
            trace_id=trace_id,
            task_id=task.task_id,
            component_id="cognitive_loop",
            blueprint_capability_id=goal.metadata.get("blueprint_capability_id") if goal.metadata else None,
            target_module="quentin/cognitive/loop_impl.py",
            target_symbol="CognitiveLoop.run_goal",
            success=done_result.is_done if done_result else False,
            error_type=None,
            error_message=None,
            start_time=start_ts,
            end_time=now_utc_iso(),
            metrics={
                "done_confidence": done_result.confidence if done_result else 0.0,
                "cost_tokens": float((metrics or {}).get("cost_tokens", 0.0)),
                "latency_ms": float((metrics or {}).get("latency_ms", 0.0)),
                "total_attempts": (metrics or {}).get("total_attempts", 0),
            },
            tags={"domain": task.domain, "environment": task.environment},
        )
        loop.traces_store.append(trace)
    except Exception:
        logger.exception("CognitiveLoop._write_trace failed")


def write_memory(
    loop: Any,
    *,
    task: Any,
    final_output: str,
    plan_summary: str,
    actions_summary: str,
    done_result: Optional[Any],
) -> None:
    try:
        content = f"Plan:\\n{plan_summary}\\n\\nActions:\\n{actions_summary}\\n\\nFinal:\\n{final_output}"
        entry = loop.memory_fabric.remember_atomic(
            content=content,
            source=f"cognitive_loop:{task.task_id}",
            tier=MemoryTier.MTS,
            importance=done_result.confidence if done_result else 0.0,
            tags=[task.domain, task.environment],
        )

        try:
            from quentin.memory.export import get_memory_exporter

            exporter = get_memory_exporter(repo_root=loop.repo_root)
            exporter.export_entry(entry)
        except Exception as e:
            logger.debug("CognitiveLoop: Memory export failed: %s", e)

        if done_result and done_result.is_done and loop.memory_fabric.graph_extractor:
            try:
                asyncio.create_task(loop.memory_fabric.graph_extractor.extract_and_store(content))
            except Exception:
                pass
    except Exception:
        logger.exception("CognitiveLoop._write_memory failed")


def apply_immune_action(loop: Any, *, action: Any, goal: Any) -> None:
    logger.warning(
        "CognitiveLoop: ImmuneAction for goal %s: %s",
        getattr(goal, "goal_id", None),
        action.to_dict(),
    )

    if action.degrade_mode:
        if not loop.degrade_mode:
            logger.warning("CognitiveLoop: entering DEGRADE MODE")
        loop.degrade_mode = True

    if action.disable_self_programming:
        if loop.self_programming_enabled:
            logger.warning("CognitiveLoop: disabling self-programming (per immune action)")
        loop.self_programming_enabled = False

    try:
        anomaly_type = str((action.anomaly or {}).get("anomaly_type") or "")
    except Exception:
        anomaly_type = ""
    if anomaly_type == "prediction_error_spike" and loop.perception_layer is not None:
        try:
            cfg = getattr(loop.perception_layer, "config", None)
            if cfg is not None:
                if getattr(cfg, "enable_situation_to_skill", False):
                    logger.warning("CognitiveLoop: disabling situation->skill reflex (per immune action)")
                    cfg.enable_situation_to_skill = False
                if getattr(cfg, "enable_expectation_engine", False):
                    logger.warning("CognitiveLoop: disabling expectation engine (per immune action)")
                    cfg.enable_expectation_engine = False
        except Exception:
            pass

    if action.revert_version:
        logger.warning(
            "CognitiveLoop: ImmuneAction suggests reverting to last stable version. "
            "This must be handled by SafetyKernel/Deployment system."
        )


async def flush_memory(loop: Any, *, goal: Any, session_id: str) -> None:
    try:
        question = CouncilQuestion(
            topic="memory_flush",
            importance="medium",
            prompt=(
                "Current context is nearing its limit and will be compacted soon.\n"
                "Extract and summarize any lasting facts, decisions, or progress from this session "
                "that must be remembered long-term.\n"
                "Return ONLY a JSON object under the 'answer' field with structure:\n"
                "{\n"
                '  "summary": "string",\n'
                '  "tags": ["string", ...]\n'
                "}\n"
            ),
            payload={"goal_id": goal.goal_id, "session_id": session_id},
        )

        decision = loop.council_manager.run_council("memory_flush", question)
        ans = decision.final.get("answer")
        if isinstance(ans, str):
            try:
                ans = json.loads(ans)
            except Exception:
                ans = {}

        if ans and ans.get("summary"):
            logger.info("CognitiveLoop: Flushing memory for session %s", session_id)
            loop.memory_fabric.remember_atomic(
                content=f"Memory Flush (Pre-Compaction):\n{ans['summary']}",
                source=f"memory_flush:{session_id}",
                tier=MemoryTier.STS,
                importance=0.7,
                tags=(ans.get("tags", []) or []) + ["flush", "pre-compaction"],
                metadata={"goal_id": goal.goal_id, "session_id": session_id},
            )
    except Exception as e:
        logger.warning("CognitiveLoop: Memory flush failed: %s", e)
