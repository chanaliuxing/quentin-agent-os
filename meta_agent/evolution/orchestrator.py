from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import os
import uuid

from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event

# The integration tests patch these symbols at import sites. Keep them as imports
# (not inline placeholder class definitions).
from meta_agent.observability.service import ObservabilityService
from meta_agent.research.api import ResearchAPI
from meta_agent.research.meta_planner import MetaResearchAgent
from meta_agent.blueprint.self_update_v2 import BlueprintSelfUpdateEngineV2, BlueprintSelfUpdateConfig
from meta_agent.memory.fabric import MemoryFabric
from meta_agent.evolution.budget import BudgetManager, default_budget_manager
from meta_agent.evolution.actions import SelfEvoActionScheduler
from meta_agent.evolution.code_tool_backend_stub import CodeToolBackend
from meta_agent.research.web_research import WebResearchWorker
from meta_agent.evolution.code_refactor import CodeRefactorWorker
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator

# Blueprint improvement loop (currently a thin integration layer).
from meta_agent.evolution.blueprint_loop import (
    BlueprintImprovementLoop,
    BlueprintStore,
    BlueprintGapTracker,
    PatchEvaluator,
    PatchGovernanceCouncil,
    PatchApplier,
    MetricsSnapshotProvider,
    ImmuneLoop,
)
from meta_agent.blueprint.objectives import ObjectiveLoader
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2


trace = JsonlTraceRecorder(repo_root=os.getcwd())


@dataclass
class SelfEvolutionConfig:
    blueprint_path: str = "blueprint/blueprint_v2.yml"
    project_root: str = "."
    mode: str = "daily"
    max_code_gaps_per_tick: int = 3
    max_blueprint_patches_per_tick: int = 1
    allow_auto_apply_code: bool = False
    allow_auto_apply_blueprint: bool = False


class SelfEvolutionOrchestrator:
    """
    Meta-Agent self-evolution orchestration layer.

    Goals:
    - Provide a stable API used by scripts and integration tests.
    - Keep wiring explicit (dependencies are importable & patchable).
    - Persist minimal state via ScheduleStateStore (used by Observability).
    """

    def __init__(
        self,
        *,
        config: Optional[SelfEvolutionConfig] = None,
        budget_manager: Optional[BudgetManager] = None,
        token_budget_config: Any = None,
    ) -> None:
        self.config = config or SelfEvolutionConfig()
        self.budget = budget_manager or default_budget_manager()

        self.obs = ObservabilityService()
        self.research_api = ResearchAPI(storage_backend=None)
        self.memory = MemoryFabric()

        self.blueprint_engine = BlueprintSelfUpdateEngineV2(
            config=BlueprintSelfUpdateConfig(blueprint_path=Path("blueprint.md")),
        )
        self.meta_research_agent = MetaResearchAgent(
            observability=self.obs,
            research_api=self.research_api,
            blueprint_engine=self.blueprint_engine,
            memory=self.memory,
        )

        self.code_backend = CodeToolBackend()
        self.web_worker = WebResearchWorker()
        self.code_refactor_worker = CodeRefactorWorker(repo_root=self.config.project_root)
        self.patch_flow = PatchFlowOrchestrator()

        class _NoopSelfProgramming:
            def run_for_gaps(self, gaps, backend: Optional[str] = None) -> None:  # noqa: ANN001
                return

        # Action handlers: keep keys aligned with ActionKind in `meta_agent.evolution.actions`.
        handlers = {
            "web_research": self._handle_web_research_action,
            "code_refactor": self._handle_code_refactor_action,
            "patch_experiment": self._handle_patch_experiment_action,
            "blueprint_update": self._handle_blueprint_update_action,
        }
        self.action_scheduler = SelfEvoActionScheduler(budget=self.budget, handlers=handlers)

        self_prog: Any = _NoopSelfProgramming()
        if os.environ.get("META_AGENT_ENABLE_SELF_PROGRAMMING", "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                self_prog = SelfProgrammingEngineV2()
            except Exception:
                # Keep the cycle runnable even if self-programming dependencies are missing.
                self_prog = _NoopSelfProgramming()

        # Blueprint improvement loop: a separate "gap -> patch" path.
        # Tests patch this class; keep instantiation local.
        self.blueprint_loop = BlueprintImprovementLoop(
            blueprint_store=BlueprintStore(),
            gap_tracker=BlueprintGapTracker(),
            self_prog=self_prog,
            patch_evaluator=PatchEvaluator(),
            patch_governance=PatchGovernanceCouncil(),
            patch_applier=PatchApplier(),
            metrics_provider=MetricsSnapshotProvider(),
            immune_loop=ImmuneLoop(),
            memory=self.memory,  # type: ignore[arg-type]
            objective_loader=ObjectiveLoader(),
        )

    # -------------------------
    # Public APIs (scripts)
    # -------------------------

    def run_tick(self) -> Dict[str, Any]:
        if self.config.mode == "daily":
            return self.run_daily_self_evo_cycle()
        return self.run_daily_self_evo_cycle()

    def run_daily_self_evo_cycle(self) -> Dict[str, Any]:
        """
        Run a single orchestration cycle.

        This method is intentionally synchronous: self-programming / patchflow / blueprint
        update steps can be async internally, but the orchestrator is called from CLI tools.
        """
        snapshot_obj = self.obs.build_snapshot()
        snapshot = snapshot_obj.to_dict() if hasattr(snapshot_obj, "to_dict") else dict(snapshot_obj)

        research_plan = self.meta_research_agent.run_cycle()
        plan_dict = research_plan.to_dict() if hasattr(research_plan, "to_dict") else {"summary": getattr(research_plan, "summary", "")}

        try:
            blueprint_improvement = self.blueprint_loop.run(snapshot=snapshot, max_sections=3)
        except Exception as e:  # noqa: BLE001
            blueprint_improvement = {"status": "error", "error": repr(e)}

        candidate_actions = []
        for task in getattr(research_plan, "tasks", []) or []:
            for a in getattr(task, "actions", []) or []:
                candidate_actions.append(
                    {
                        "kind": getattr(a, "kind", "other_note"),
                        "priority": 5,
                        "estimated_tokens": 10_000,
                        "payload": getattr(a, "target", {}) or {},
                    }
                )

        selected_actions = self.action_scheduler.schedule(candidate_actions)
        action_results = [self._dispatch_action(a) for a in selected_actions]

        summary = {
            "snapshot": snapshot,
            "research_plan": plan_dict,
            "blueprint_improvement": blueprint_improvement,
            "selected_actions": [getattr(a, "kind", None) for a in selected_actions],
            "action_results": action_results,
        }

        trace.record_event(
            new_trace_event(
                trace_id=f"self-evo-{uuid.uuid4().hex[:8]}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "self_evo_cycle_done", "summary": summary},
            )
        )
        return summary

    # -------------------------
    # Internal: dispatch/handlers
    # -------------------------

    def _dispatch_action(self, act: Any) -> Dict[str, Any]:
        kind = getattr(act, "kind", None) or (act.get("kind") if isinstance(act, dict) else None)
        if not kind:
            return {"status": "skipped", "reason": "missing_kind"}
        handler = getattr(self.action_scheduler, "handlers", {}).get(kind)
        if not handler:
            return {"status": "skipped", "reason": f"no_handler:{kind}"}
        try:
            return handler(act)
        except Exception as e:  # noqa: BLE001
            trace.record_event(
                new_trace_event(
                    trace_id=f"self-evo-{uuid.uuid4()}",
                    event_type=TraceEventType.ERROR,
                    payload={"action_kind": kind, "error": repr(e)},
                )
            )
            return {"status": "error", "kind": kind, "error": repr(e)}

    def _handle_code_refactor_action(self, act: Any) -> Dict[str, Any]:
        return {"status": "skipped", "reason": "not_wired_yet"}

    def _handle_web_research_action(self, act: Any) -> Dict[str, Any]:
        return {"status": "skipped", "reason": "not_wired_yet"}

    def _handle_patch_experiment_action(self, act: Any) -> Dict[str, Any]:
        payload = getattr(act, "payload", None) if not isinstance(act, dict) else act.get("payload")
        return self.patch_flow.run_experiment_for_action(payload)

    def _handle_blueprint_update_action(self, act: Any) -> Dict[str, Any]:
        return {"status": "skipped", "reason": "blueprint_update_disabled"}
