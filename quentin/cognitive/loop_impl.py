from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from pathlib import Path
import logging
from quentin.council.manager import CouncilManager
from quentin.council.done import DoneCouncil
from quentin.council.reflection import ReflectionCouncil
from quentin.skills.manager import SkillManager
from quentin.tools.manager import ToolManager
from quentin.immune.loop import ImmuneLoop
from quentin.models.router import ModelRouter
from quentin.goals.done_definition import GoalDoneManager
from quentin.memory.fabric import MemoryFabric
from quentin.memory.session_deltas import SessionDeltaConfig
from quentin.kernel.safety import SafetyKernel
from quentin.traces.execution_trace import ExecutionTraceStore
from quentin.runtime.system_events import SystemEventQueue
from quentin.config.cognitive_policies import CognitivePolicies
from quentin.cognitive.loop_maintenance import initialize_loop as maintenance_initialize_loop
from quentin.cognitive.loop_entrypoints import run_task as entry_run_task, run_task_async as entry_run_task_async
from quentin.cognitive.loop_api_shims import install_loop_shims
from quentin.cognitive.loop_runtime_shims import install_loop_tail_shims
from quentin.cognitive.loop_models import (
    CognitiveResult,
    CognitiveTask,
    ExecutorFn,
    PlannerFn,
    PlannerResult,
)
from quentin.traces.core import TraceEvent

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quentin.cognitive.perception.layer import PerceptionContextLayer

try:
    from quentin.skills.miner import SkillMiner  # type: ignore
except Exception:  # noqa: BLE001
    SkillMiner = None  # type: ignore[assignment]


# ---- CognitiveLoop 主体 ----

class CognitiveLoop:
    """
    CognitiveLoop v2:

    流程：
        1. 根据 CognitiveTask 生成 GoalSpec（写入 GoalStore）
        2. 调用 Planner (via Planner Council) 生成 plan
        3. 调用 Executor (via Skill/LLM) 执行
        4. 构造 DoneCheckContext，由 DoneCouncil 评估“是否完成”
        5. 若未完成且失败多次，触发 ReflectionCouncil 进行反省，调整计划
        6. 写 ExecutionTrace
        7. 写入 MemoryFabric（短期记忆）
        8. 返回 CognitiveResult
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        planner: Optional[PlannerFn] = None,
        executor: Optional[ExecutorFn] = None,
        perception_layer: Optional[PerceptionContextLayer] = None,
        cognitive_policies: Optional[CognitivePolicies] = None,
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
        maintenance_initialize_loop(
            self,
            repo_root=repo_root,
            planner=planner,
            executor=executor,
            perception_layer=perception_layer,
            cognitive_policies=cognitive_policies,
            goal_manager=goal_manager,
            memory_fabric=memory_fabric,
            traces_store=traces_store,
            skill_manager=skill_manager,
            model_router=model_router,
            done_council=done_council,
            reflection_council=reflection_council,
            immune_loop=immune_loop,
            safety_kernel=safety_kernel,
            session_delta_config=session_delta_config,
            system_event_queue=system_event_queue,
            council_manager=council_manager,
            tool_manager=tool_manager,
            self_programming_engine=self_programming_engine,
        )

    # ---- 对外统一入口 ----

    async def run_task_async(self, task: CognitiveTask) -> CognitiveResult:
        return await entry_run_task_async(self, task=task, cognitive_result_cls=CognitiveResult)

    def run_task(self, task: CognitiveTask) -> CognitiveResult:
        return entry_run_task(self, task=task, cognitive_result_cls=CognitiveResult)

    def run_goal(self, task: CognitiveTask) -> CognitiveResult:
        session_id = (task.metadata or {}).get("session_id") if isinstance(task.metadata, dict) else task.task_id
        
        # P0: Lane orchestration entrypoint (replaces direct enqueue calls)
        from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
        
        async def _wrapper():
            return await self._run_goal_internal(task)
            
        try:
            return lane_orchestrator.run_sync(str(session_id), _wrapper)
        except RuntimeError:
            # Fallback if already in an event loop (e.g. from fastAPI)
            # In a real app, this should be awaited, but for CLI wrapper compatibility we might need to block.
            # However, asyncio.run fails if loop is running.
            # If we are here, we are likely the top-level CLI.
            raise

    # thin wrapper methods are installed via `install_loop_shims` at module tail.

    # tail helper methods are installed via `install_loop_tail_shims` at module tail.


install_loop_shims(CognitiveLoop)
install_loop_tail_shims(CognitiveLoop)

__all__ = [
    "CognitiveLoop",
    "CognitiveTask",
    "CognitiveResult",
    "PlannerResult",
    "SkillMiner",
    "TraceEvent",
]
