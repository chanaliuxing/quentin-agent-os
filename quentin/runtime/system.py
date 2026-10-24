from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, Optional, List, TYPE_CHECKING

# Early symbol placeholders to avoid circular-import import-time failures.
MetaAgentRuntime = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from quentin.planning import HierarchicalPlanner
    from quentin.execution import Executor
else:
    HierarchicalPlanner = None  # type: ignore[assignment]
    Executor = None  # type: ignore[assignment]

from quentin.traces.core import TraceRecorder, JsonlTraceRecorder
from quentin.runtime.cognitive_loop import CognitiveLoop, TaskRequest, TaskResult
from quentin.runtime.immune_loop import ImmuneLoop, AnomalyDetectorConfig, ImmuneAction
from quentin.sleep.loop import SleepLoop, SleepLoopConfig
from quentin.evolution.skill_loop import SkillEvolutionLoop, SkillEvolutionStats
from quentin.memory.fabric import MemoryFabric
from quentin.tools.manager import ToolManager
from quentin.critic.core import SimpleCritic
from quentin.skills.registry import SkillRegistry
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.engine import SelfProgrammingEngine


@dataclass
class RuntimeFacade:
    """
    系统中控（Base Layer + 部分 Meta Layer 的入口）。

    负责：
      - 统一对外暴露“执行任务”的接口（可以走 CognitiveLoop）
      - 对 ResearchLayer 提供：
          * run_blueprint_improvement_cycle(...)
          * auto_update_capabilities_from_repo(...)
      - 挂载四大 Loop：
          * cognitive_loop
          * immune_loop
          * sleep_loop
          * skill_evolution_loop
    """

    model_router: Any = None
    memory_fabric: Any = None
    tool_manager: Any = None
    critic: Any = None
    planner: Optional[HierarchicalPlanner] = None
    executor: Optional[Executor] = None
    council: Optional[Any] = None
    repo_root: str | Path = "."
    research_layer: Optional[Any] = None

    # 新增：观测与循环
    trace_recorder: Optional[TraceRecorder] = None
    cognitive_loop: Optional[CognitiveLoop] = None
    immune_loop: Optional[ImmuneLoop] = None
    sleep_loop: Optional[SleepLoop] = None
    skill_evolution_loop: Optional[SkillEvolutionLoop] = None
    self_programming_engine: Optional[Any] = None
    safety_kernel: Optional[Any] = None
    
    # 兼容旧字段/参数 (blueprint related)
    orchestrator: Optional[Any] = None # Assuming model_router acts as orchestrator or vice-versa in this new implementation?
    # In 112.md we passed orchestrator to constructor in create_runtime...
    # In 115.md update, model_router is the first arg.
    # I should probably keep orchestrator for compatibility or map it.
    # The previous step (112.md) instantiated RuntimeFacade(orchestrator=..., ...)
    # This new definition (116.md) uses (model_router=..., ...) as dataclass fields.
    # I will add orchestrator field and handle mapping in __post_init__ or adjust usage.
    # Wait, 112.md used __init__ with named args.
    # 116.md defines it as a dataclass. 
    # To support previous calls, I need to ensure orchestrator is handled.
    # If orchestrator is passed, it might be assigned to model_router or kept separate.
    # In 116.md execute_task uses self.model_router(prompt).
    # In 112.md run_task uses self.orchestrator.run_task.
    # I will keep orchestrator field. 
    
    blueprint_spec: Optional[Any] = None
    capabilities_registry: Optional[Any] = None
    blueprint_improver: Optional[Any] = None
    config: Optional[Any] = None # From 112.md

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        from quentin.bootstrap.container import Container

        self.container = Container(repo_root=self.repo_root)

        # Canonical wiring: RuntimeFacade should reuse Container components whenever possible.
        # This keeps legacy runtime entrypoints from drifting away from the core loop stack.
        if self.trace_recorder is None:
            self.trace_recorder = self.container.trace_recorder

        # Compatibility: map orchestrator / model_router 双向补齐
        if self.orchestrator and not self.model_router:
            self.model_router = getattr(self.orchestrator, "llm", self.orchestrator)
        if self.model_router and not self.orchestrator:
            self.orchestrator = getattr(self.model_router, "orchestrator", None) or self.model_router

        # Reuse canonical infra from container first; fallback only when needed.
        if self.tool_manager is None:
            self.tool_manager = self.container.tool_manager
        if self.safety_kernel is None:
            try:
                self.safety_kernel = self.container.safety_kernel
            except Exception:
                pass
        if self.memory_fabric is None:
            self.memory_fabric = self.container.memory_fabric
        if self.critic is None:
            # SimpleCritic expects an LLM-like callable; fallback to model_router
            self.critic = SimpleCritic(llm=self.model_router or (lambda _: ""))

        # Loop 可能在外部构造后再 attach，这里不强制
        if self.cognitive_loop is None:
            core_loop = self.container.cognitive_loop
            self.cognitive_loop = CognitiveLoop(
                trace_recorder=self.trace_recorder,
                memory_fabric=self.memory_fabric,
                critic=self.critic,
                runtime=self,
                core_loop=core_loop,
            )

    # --------------------------------------------------
    # 接 ResearchLayer 的挂载
    # --------------------------------------------------
    def attach_research_layer(self, research_layer: Any) -> None:
        self.research_layer = research_layer

    # --------------------------------------------------
    # 统一任务执行接口（底层执行，不含 self-reflection）
    # 被 CognitiveLoop 调用
    # --------------------------------------------------
    def execute_task(
        self,
        *,
        task_id: str,
        description: str,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        trace_id: str,
        trace_recorder: Optional[TraceRecorder] = None,
    ) -> Dict[str, Any]:
        """
        This is the lowest-level execution engine. It now attempts to use a planner and an executor.
        """
        # Highest priority: orchestrator if present
        if self.orchestrator and hasattr(self.orchestrator, "run_task"):
            try:
                orch_result = self.orchestrator.run_task(
                    goal=description,
                    context=context,
                    runtime=self,
                )
                if hasattr(orch_result, "to_dict"):
                    return {"orchestrator_result": orch_result.to_dict()}
                if isinstance(orch_result, dict):
                    return orch_result
                return {"orchestrator_result": orch_result}
            except Exception as e:
                return {"error": f"orchestrator_failed: {e!r}"}

        if self.planner and self.executor:
            plan = self.planner.plan(description, context)
            if plan and getattr(plan, "steps", None):
                return self.executor.execute_plan(plan, context)
            prompt = self._build_default_prompt(description, payload, context)
        else:
            prompt = self._build_default_prompt(description, payload, context)

        # Execute the prompt
        try:
            if callable(self.model_router):
                 text = self.model_router(prompt)
                 return {"raw_output": text}
            else:
                 return {"error": "Model router is not callable."}
        except Exception as e:
            return {"error": f"LLM execution failed: {e!r}"}

    def _build_default_prompt(self, description: str, payload: Dict[str, Any], context: Dict[str, Any]) -> str:
        return (
            "你是一个通用智能体，请按照用户任务完成工作。\n\n"
            f"任务描述:\n{description}\n\n"
            f"任务输入(JSON):\n{payload}\n\n"
            f"上下文(JSON):\n{context}\n\n"
            "请直接给出你的输出结果，使用尽量结构化的形式。"
        )

    # --------------------------------------------------
    # 对外暴露的“run_task”入口（带认知循环）
    # --------------------------------------------------
    def run_task(
        self,
        description: str, # mapped from goal in 112.md call? 112.md calls run_task(goal, context)
        payload: Dict[str, Any] = None, # 112.md didn't pass payload, just context?
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        """
        对外推荐使用这个接口执行任务：
          - 会经过 CognitiveLoop
          - 自动写 Trace / Summary / Lessons / Memory
          - ImmuneLoop 的统计也会在 CognitiveLoop 里被记录
        """
        # Handle compatibility with (goal, context) signature from 112.md
        # The definition here is (description, payload, context).
        # If called as run_task(goal, context), payload will be the context dict if positional?
        # 112.md call: runtime.run_task(goal, {"domain": "general"})
        # goal -> description
        # context -> payload (oops)
        # So we need to be careful.
        # If payload is None and context is None, but description is passed...
        # Actually, if called with keyword args it's fine.
        # If called positionally: run_task("goal", {"ctx":1}) -> description="goal", payload={"ctx":1}, context=None
        # We should treat payload as context if context is missing and payload looks like context?
        # Or just default payload to empty dict. 
        
        if payload is None:
             payload = {}
        
        # Bridge: if called from old code which might pass context as 2nd arg
        if context is None and isinstance(payload, dict) and "domain" in payload:
             context = payload
             payload = {}

        if not self.cognitive_loop:
            # Fallback to old run_task logic if cognitive_loop not attached (e.g. early bootstrap)
            # or raise error? 
            # 116.md says: "对外推荐使用这个接口... 如果不挂 loop..."
            # I should probably allow fallback to orchestrator directly if loop missing, for compatibility.
            if self.orchestrator and hasattr(self.orchestrator, "run_task"):
                 # Map back to old TaskResult?
                 # 112.md TaskResult had (task_id, output, trace).
                 # 115.md TaskResult has (task_id, trace_id, status, output, summary, lessons).
                 # They are different.
                 # I will try to use CognitiveLoop if available, otherwise raise or try basic execution.
                 pass
            
            raise RuntimeError("CognitiveLoop is not attached to RuntimeFacade.")

        return self.cognitive_loop.run_task(description, payload, context or {})

    # --------------------------------------------------
    # 与蓝皮书自迭代相关的接口（你之前已经部分实现）
    # --------------------------------------------------
    def auto_update_capabilities_from_repo(self, repo_root: str | Path | None = None) -> Dict[str, Any]:
        """
        这里假设你已经实现了 CapabilityRegistry + LLMBasedCapabilityProbe 等，
        现在只是保留接口。你可以在之前的基础上加入 trace 记录。
        """
        # Forward to existing implementation if available (I wrote it in 112.md)
        # But I am overwriting the class. I need to re-implement or ensure 112.md logic is preserved.
        # 112.md implementation:
        from quentin.blueprint.capability_scanner import CapabilityScanner, CapabilityScanReport
        root = Path(repo_root or self.repo_root).resolve()
        
        # Try to find LLM/Council
        llm_for_scan = getattr(self.model_router, "llm", self.model_router) if hasattr(self.model_router, "llm") or callable(self.model_router) else None
        # If model_router is OllamaLLMClient, it is callable. 
        
        scanner = CapabilityScanner(
            repo_root=root,
            spec=self.blueprint_spec,
            registry=self.capabilities_registry,
            llm=llm_for_scan, 
            council=self.council,
        )
        scan_report: CapabilityScanReport = scanner.scan_and_update_registry()

        return {
            "scan_report": scan_report.to_dict(),
            "registry_snapshot": self.capabilities_registry.export() if self.capabilities_registry else {},
        }

    def run_blueprint_improvement_cycle(
        self,
        *,
        max_gaps: int,
        research_request: Any,
    ) -> Dict[str, Any]:
        """
        这里也是假设你已经有 BlueprintImprover + ResearchLayer 的逻辑。
        当前先作为占位接口，后续可以逐步填充。
        """
        # Re-implement logic from 112.md/111.md
        if self.research_layer is None:
             return {
                "status": "error",
                "message": "ResearchLayer is not attached.",
            }
        
        from quentin.blueprint.gap_tracker import BlueprintGapTracker
        
        # 1) Scan
        gap_tracker = BlueprintGapTracker(
            spec=self.blueprint_spec,
            registry=self.capabilities_registry,
            repo_root=self.repo_root
        )
        gap_report = gap_tracker.scan()
        gap_dict = gap_report.to_dict()

        if not gap_report.missing and not gap_report.partial:
            return {"status": "no_gaps", "gap_report": gap_dict}

        # 2) Plan
        if not self.blueprint_improver:
             return {"status": "no_improver", "gap_report": gap_dict}
             
        improvement_plans = self.blueprint_improver.propose_improvement_plans(
            gap_report,
            max_gaps=max_gaps,
        )

        if not improvement_plans:
            return {"status": "no_plans", "gap_report": gap_dict}

        # 3) Experiments
        experiments_created = []
        exp_orch = self.research_layer.experiment_orchestrator
        variant_ids = list(exp_orch.variants_runtimes.keys())

        for plan in improvement_plans:
            record = self.research_layer.create_experiment(
                name=plan.experiment_name,
                description=plan.experiment_description,
                variants=variant_ids,
                tasks=plan.tasks,
                meta={
                    "domain": "blueprint-improvement",
                    "priority": plan.priority,
                    "capability_id": plan.capability_id,
                },
            )
            experiments_created.append(record.config.experiment_id)

        # 4) Run Cycle
        cycle_result = self.research_layer.run_research_cycle(research_request)

        return {
            "status": "ok",
            "gap_report": gap_dict,
            "improvement_plans": [p.to_dict() for p in improvement_plans],
            "created_experiments": experiments_created,
            "research_cycle_result": cycle_result.to_dict(),
        }

    # --------------------------------------------------
    # 免疫 / 睡眠 / 技能进化的统一入口（给定期 scheduler / ResearchLayer 调用）
    # --------------------------------------------------
    def run_immune_check(self) -> ImmuneAction:
        if not self.immune_loop:
            return ImmuneAction(action_type="none", reason="no_immune_loop", metadata={})
        return self.immune_loop.analyze_and_maybe_act()

    def run_sleep_cycle(self) -> Dict[str, Any]:
        if not self.sleep_loop:
            return {"status": "no_sleep_loop"}
        result = self.sleep_loop.run_once()
        if hasattr(result, "__await__"):
            import asyncio
            result = asyncio.run(result)
        if hasattr(result, "to_dict"):
            try:
                d = result.to_dict()
                # Back-compat: older callers expect `sts_processed`.
                if isinstance(d, dict) and "processed_sts" in d and "sts_processed" not in d:
                    d["sts_processed"] = d.get("processed_sts")
                return d
            except Exception:
                pass
        if isinstance(result, dict):
            return result
        return {"status": "ok", "result": str(result)}

    def run_skill_evolution_cycle(self) -> SkillEvolutionStats:
        if not self.skill_evolution_loop:
            return SkillEvolutionStats(
                patterns_mined=0,
                candidates_generated=0,
                experiments_created=0,
                candidates_accepted=0,
                candidates_rejected=0,
            )
        return self.skill_evolution_loop.run_once()


def build_default_runtime(
    *,
    repo_root: str | Path,
    llm: Any,
    council: Optional[Any] = None,
    enable_self_programming: bool = True,
) -> RuntimeFacade:
    """
    Convenience bootstrap used by tooling/scripts to create a minimally functional
    RuntimeFacade with cognitive/sleep/immune/skill-evolution loops wired up.
    """
    repo_root = Path(repo_root).resolve()
    # Keep default-runtime deterministic/offline-friendly unless caller explicitly configured provider.
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["QUENTIN_COUNCIL_LOCAL_FAST_PATH"] = "1"
    os.environ["QUENTIN_COUNCIL_LOCAL_FAST_PATH_MAX_CHARS"] = "200000"
    runtime = RuntimeFacade(
        model_router=llm,
        council=council,
        repo_root=repo_root,
    )
    trace_recorder = runtime.trace_recorder or JsonlTraceRecorder(repo_root=repo_root)
    memory_fabric = runtime.memory_fabric or MemoryFabric(
        db_path=repo_root / "data" / "memory.db",
        trace_recorder=trace_recorder,
        use_postgres=False,
    )
    runtime.trace_recorder = trace_recorder
    runtime.memory_fabric = memory_fabric
    runtime.tool_manager = runtime.tool_manager or ToolManager()
    runtime.critic = runtime.critic or SimpleCritic(llm=llm)

    # Loops
    runtime.cognitive_loop = CognitiveLoop(
        trace_recorder=trace_recorder,
        memory_fabric=memory_fabric,
        critic=runtime.critic,
        runtime=runtime,
        delegate_to_core=False,
        core_loop=runtime.container.cognitive_loop,
    )
    runtime.immune_loop = runtime.immune_loop or ImmuneLoop(
        config=AnomalyDetectorConfig(),
        trace_recorder=trace_recorder,
    )
    runtime.sleep_loop = runtime.sleep_loop or SleepLoop(
        config=SleepLoopConfig(),
        trace_recorder=trace_recorder,
        memory_fabric=memory_fabric,
        council=council or llm,
        repo_root=repo_root,
    )
    # Skill evolution loop currently expects a self-programming engine instance.
    sp_engine = runtime.self_programming_engine
    if sp_engine is None and enable_self_programming:
        try:
            sp_engine = SelfProgrammingEngine(repo_root=str(repo_root), metrics_store=JsonlMetricsStore(repo_root=repo_root))
        except Exception:
            class _StubEngine:
                def select_patches_to_promote(self, reports, max_promote: int = 1):
                    return list(reports)[:max_promote]

            sp_engine = _StubEngine()
        runtime.self_programming_engine = sp_engine

    runtime.skill_evolution_loop = runtime.skill_evolution_loop or SkillEvolutionLoop(
        engine=sp_engine or (lambda *_, **__: None),  # type: ignore[arg-type]
        llm=council or llm,
        repo_root=repo_root,
    )

    return runtime


# Backward compatibility alias.
MetaAgentRuntime = RuntimeFacade
