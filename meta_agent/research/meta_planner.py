# meta_agent/research/meta_planner.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import datetime as dt
import json
import uuid
import os

# Existing Imports
from meta_agent.observability.service import ObservabilityService
from meta_agent.observability.snapshot import SystemSnapshot
from meta_agent.research.api import ResearchAPI
from quentin.traces.core import JsonlTraceRecorder
from meta_agent.blueprint.self_update_v2 import BlueprintSelfUpdateEngineV2
from meta_agent.blueprint.patch_types import BlueprintPatch, make_blueprint_patch_id

# New Imports for Objectives and Council
from meta_agent.blueprint.store import BlueprintCoverageStore
from meta_agent.blueprint.objectives import ObjectiveLoader
from meta_agent.blueprint.objective_eval import BlueprintObjectiveEvaluator, ObjectiveEvalResult, SectionPriority
from meta_agent.memory.fabric import MemoryFabric, MemoryTier
from meta_agent.runtime import council # New council import
import asyncio
import socket

trace = JsonlTraceRecorder(repo_root=".")

# ... (Dataclasses ResearchActionSpec, ResearchTaskSpec, ResearchPlan remain the same) ...
@dataclass
class ResearchActionSpec:
    kind: str
    description: str
    target: Dict[str, Any] = field(default_factory=dict)
    config_suggestion: Optional[Dict[str, Any]] = None

@dataclass
class ResearchTaskSpec:
    id: str; title: str; focus_area: str; priority: str; rationale: str
    actions: List[ResearchActionSpec] = field(default_factory=list)

@dataclass
class ResearchPlan:
    generated_at: str; summary: str
    tasks: List[ResearchTaskSpec] = field(default_factory=list)


class MetaResearchAgent:
    def __init__(
        self,
        observability: ObservabilityService,
        research_api: ResearchAPI,
        blueprint_engine: Optional[BlueprintSelfUpdateEngineV2] = None,
        coverage_store: Optional[BlueprintCoverageStore] = None,
        objective_loader: Optional[ObjectiveLoader] = None,
        memory: Optional[MemoryFabric] = None,
        obj_evaluator: Optional[BlueprintObjectiveEvaluator] = None,
    ):
        self.observability = observability
        self.research_api = research_api
        self.blueprint_engine = blueprint_engine
        self.coverage_store = coverage_store or BlueprintCoverageStore()
        self.objective_loader = objective_loader or ObjectiveLoader()
        self.memory = memory or MemoryFabric()
        self.obj_evaluator = obj_evaluator or BlueprintObjectiveEvaluator()

    def run_cycle(self) -> ResearchPlan:
        snapshot = self.observability.build_snapshot()
        coverage = self.coverage_store.load_current()
        objectives = self.objective_loader.load()
        
        eval_result = None
        if coverage and objectives:
            eval_result = self.obj_evaluator.evaluate(coverage, objectives)
        
        context = self._build_research_context(snapshot, coverage, eval_result)
        
        plan_data = self._plan_with_llm(context) # Use new method signature
        
        tasks = [ResearchTaskSpec(
            id=t.get("id") or f"R-{uuid.uuid4().hex[:6]}",
            title=t.get("title", ""),
            focus_area=t.get("focus_area", "other"),
            priority=t.get("priority", "medium"),
            rationale=t.get("rationale", ""),
            actions=[ResearchActionSpec(**a) for a in t.get("actions", [])]
        ) for t in plan_data.get("tasks", [])]
        
        plan = ResearchPlan(
            generated_at=now_iso(),
            summary=plan_data.get("summary", ""),
            tasks=tasks[:5] # Limit tasks
        )
        
        self._execute_plan(plan)
        return plan

    def _build_research_context(self, snapshot: SystemSnapshot, coverage: Optional[Any], eval_result: Optional[ObjectiveEvalResult]) -> Dict[str, Any]:
        snap = snapshot.to_dict()
        context = {
            "snapshot_summary": {
                "skills": snap["skills"], "patches": snap["patches"], "gaps": snap["gaps"],
                "research": snap["research"], "blueprint_effects": snap["blueprint_effects"],
            },
            "coverage_summary": coverage.summary.to_dict() if coverage else {},
            "objective_eval_global": eval_result.global_status.__dict__ if eval_result and eval_result.global_status else {},
            "top_priority_sections": [p.__dict__ for p in eval_result.section_priorities[:5]] if eval_result else [],
        }
        return context

    def _plan_with_llm(self, context: Dict[str, Any]) -> Dict[str, Any]:
        question = "Based on the current system status and objective evaluation, formulate a 1-7 day research roadmap."
        schema_hint = """
        Output a JSON object with keys "summary" (string) and "tasks" (array of objects).
        Each task object should have keys: "id", "title", "focus_area", "priority", "rationale", "actions".
        Each action object should have keys: "kind", "description", "target", "config_suggestion".
        """
        # Zero-config behavior: do not block on LLM by default.
        # Enable by setting `META_AGENT_ENABLE_META_RESEARCH_LLM=1`.
        if os.environ.get("META_AGENT_ENABLE_META_RESEARCH_LLM", "").strip().lower() not in ("1", "true", "yes", "on"):
            return {"summary": "fallback_llm_disabled", "tasks": []}

        # If no local council backend is reachable, do not block.
        # CouncilRuntime defaults to Ollama at localhost:11434.
        try:
            with socket.create_connection(("localhost", 11434), timeout=0.2):
                pass
        except OSError:
            return {"summary": "fallback_no_local_llm", "tasks": []}

        try:
            res = council.ask_json(
                role="meta_research",
                question=question,
                context=context,
                json_schema_hint=schema_hint,
            )
            if hasattr(res, "__await__"):
                res = asyncio.run(res)  # type: ignore[assignment]
            return res if isinstance(res, dict) else {"summary": "invalid_response", "tasks": []}
        except Exception as e:  # noqa: BLE001
            trace.record_event(event_type="meta_research_plan_error", trace_id="meta_research", payload={"error": repr(e)})
            return {"summary": "fallback_due_to_error", "tasks": []}

    def _execute_plan(self, plan: ResearchPlan) -> None:
        # This logic remains the same
        for task in plan.tasks:
            for action in task.actions:
                if action.kind == "experiment":
                    self._execute_experiment_action(task, action)
                elif action.kind in ("gap_rewrite", "blueprint_patch"):
                    self._execute_blueprint_action(task, action)
                elif action.kind == "web_research":
                    self._execute_web_research_action(task, action)
                else:
                    trace.record_event(event_type="meta_research_action_note", trace_id=task.id, payload={"task_id": task.id, "kind": action.kind})
    
    # ... Other _execute_* methods ...
    def _execute_experiment_action(self, task: ResearchTaskSpec, action: ResearchActionSpec) -> None:
        target_type = str(action.target.get("target_type") or action.target.get("target_module") or "planner")
        exp_cfg = {
            "name": action.target.get("name") or f"{task.title}".strip() or f"experiment::{task.id}",
            "description": action.description or task.rationale or "",
            "target_type": target_type,
            "metrics": list(action.target.get("metrics") or ["success_rate", "avg_latency_ms"]),
            "variants": list(action.target.get("variants") or []),
        }

        try:
            rec = self.research_api.create_experiment(exp_cfg)
            exp_id = str(rec.get("experiment_id") or rec.get("id") or "")
            run = None
            if exp_id:
                run = self.research_api.run_experiment_async(exp_id)
            trace.record_event(
                event_type="meta_research_experiment_triggered",
                trace_id=task.id,
                payload={"task_id": task.id, "action": action.__dict__, "experiment": exp_cfg, "record": rec, "run": run},
            )
        except Exception as e:  # noqa: BLE001
            trace.record_event(
                event_type="meta_research_experiment_error",
                trace_id=task.id,
                payload={"task_id": task.id, "error": repr(e), "experiment": exp_cfg},
            )

    def _execute_blueprint_action(self, task: ResearchTaskSpec, action: ResearchActionSpec) -> None:
        # Default: never auto-apply blueprint changes unless explicitly enabled.
        allow_apply = os.environ.get("META_AGENT_ALLOW_BLUEPRINT_AUTO_APPLY", "").strip().lower() in ("1", "true", "yes", "on")

        patch = BlueprintPatch(
            id=make_blueprint_patch_id(),
            created_at=now_iso(),
            source="meta_research",
            author="meta_research",
            target_section=str(action.target.get("target_section") or action.target.get("section") or "unknown"),
            change_type=str(action.target.get("change_type") or "append_section"),
            old_excerpt=action.target.get("old_excerpt"),
            new_content=str(action.target.get("new_content") or action.description or ""),
            rationale=str(action.target.get("rationale") or task.rationale or ""),
            risk_level=str(action.target.get("risk_level") or "medium"),
            metadata={"task_id": task.id, "focus_area": task.focus_area},
        )

        applied = None
        try:
            if self.blueprint_engine is not None and allow_apply:
                applied = self.blueprint_engine.apply_patch(patch, auto=True)
            trace.record_event(
                event_type="meta_research_blueprint_patch_proposed",
                trace_id=patch.id,
                payload={"task_id": task.id, "action": action.__dict__, "patch": patch.__dict__, "applied": getattr(applied, "__dict__", None)},
            )
        except Exception as e:  # noqa: BLE001
            trace.record_event(
                event_type="meta_research_blueprint_patch_error",
                trace_id=patch.id,
                payload={"task_id": task.id, "error": repr(e), "patch": patch.__dict__},
            )

        # Persist an STS memory note (best-effort).
        try:
            self.memory.write_observation(
                text=f"[meta_research] blueprint_patch proposed: {patch.id} target={patch.target_section} change={patch.change_type}\n{patch.rationale}\n",
                metadata={"patch_id": patch.id, "task_id": task.id, "tags": ["meta_research", "blueprint_patch"]},
            )
        except Exception:
            return

    def _execute_web_research_action(self, task: ResearchTaskSpec, action: ResearchActionSpec) -> None:
        from meta_agent.research.web_research import WebResearchBackend, WebResearchTask

        query = str(action.target.get("query") or action.description or task.title or "")
        if not query.strip():
            return

        backend = WebResearchBackend()
        res = backend.run(
            WebResearchTask(
                query=query,
                urls=list(action.target.get("urls") or []) or None,
                focus=str(action.target.get("focus") or "paper"),
                notes=str(action.target.get("notes") or ""),
            )
        )
        trace.record_event(
            event_type="meta_research_web_research_done",
            trace_id=task.id,
            payload={"task_id": task.id, "action": action.__dict__, "query": query, "ok": res is not None},
        )

        if res is None:
            return

        try:
            self.memory.write_observation(
                text=f"[web_research] {query}\n\n{res.combined}\n",
                metadata={"task_id": task.id, "query": query, "num_summaries": len(res.summaries), "tags": ["web_research", "meta_research"]},
            )
        except Exception:
            return
