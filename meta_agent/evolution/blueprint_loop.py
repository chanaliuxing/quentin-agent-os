from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from meta_agent.blueprint.coverage import BlueprintCoverageAnalyzer, BlueprintIndexItem, BlueprintCoverageReport
from meta_agent.blueprint.objectives import ObjectiveLoader
from meta_agent.blueprint.objective_eval import BlueprintObjectiveEvaluator, ObjectiveEvalResult
from meta_agent.blueprint.store import BlueprintCoverageStore
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event

from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, GapLike


trace = JsonlTraceRecorder(repo_root=".")


class BlueprintStore:
    """
    Load a machine-readable blueprint index.

    Current repo source of truth:
    - `blueprint/meta_agent_v3.yaml` (layers/modules with dotted paths)
    """

    def __init__(self, path: str | Path = "blueprint/meta_agent_v3.yaml") -> None:
        self.path = Path(path)

    def load(self) -> List[BlueprintIndexItem]:
        # Fallback: a minimal stable index.
        base = [
            BlueprintIndexItem("memory.fabric", "memory.fabric", "Memory Fabric"),
            BlueprintIndexItem("skills.mining", "skills.mining", "Skill Mining & Promotion"),
            BlueprintIndexItem("patchflow.core", "patchflow.core", "PatchFlow Core Pipeline"),
        ]

        if not self.path.exists():
            return base

        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            return base

        extra: List[BlueprintIndexItem] = []
        for layer in raw.get("layers") or []:
            lid = layer.get("id")
            lname = layer.get("name") or lid
            for m in (layer.get("modules") or []):
                mid = m.get("id")
                if not (lid and mid):
                    continue
                sec_id = f"{lid}.{mid}"
                extra.append(BlueprintIndexItem(sec_id, sec_id, f"{lname}: {mid}"))

        # Deduplicate by section_id while preserving order.
        seen = set()
        out: List[BlueprintIndexItem] = []
        for item in [*base, *extra]:
            if item.section_id in seen:
                continue
            seen.add(item.section_id)
            out.append(item)
        return out


class BlueprintGapTracker:
    """
    Derive actionable "gaps" from a coverage report + objectives.

    This is intentionally heuristic-driven and conservative: it should never crash a cycle.
    """

    def find_gaps(
        self,
        coverage: BlueprintCoverageReport,
        objectives: Any,
        *,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        gaps: List[Dict[str, Any]] = []
        cov_by_id = {s.section_id: s for s in coverage.sections}
        sec_objs = getattr(objectives, "sections", {}) if objectives is not None else {}

        for sec_id, cov in cov_by_id.items():
            target = None
            if isinstance(sec_objs, dict) and sec_id in sec_objs:
                target = getattr(sec_objs[sec_id], "target_level", None)

            # Simple gap conditions.
            level_bad = cov.level in ("missing", "planned")
            todo_bad = int(cov.open_todos or 0) > 0 or int(cov.open_gaps or 0) > 0
            target_gap = bool(target) and str(cov.level) != str(target)

            if not (level_bad or todo_bad or target_gap):
                continue

            severity = 1
            if cov.level == "missing":
                severity = 5
            elif cov.level == "planned":
                severity = 4
            elif todo_bad:
                severity = 2

            gaps.append(
                {
                    "section_id": sec_id,
                    "kind": "coverage_gap",
                    "severity": severity,
                    "description": f"Coverage gap for {sec_id}: level={cov.level}, target={target}, todos={cov.open_todos}, gaps={cov.open_gaps}",
                    "suspect_files": [],
                    "section_priority": 0,
                }
            )

        gaps.sort(key=lambda g: (-int(g.get("severity", 1)), str(g.get("section_id", ""))))
        return gaps[:limit]


class PatchEvaluator:
    def evaluate_patch(self, patch_proposal: Any) -> Dict[str, Any]:
        return {"status": "skipped", "reason": "blueprint_loop_delegates_to_self_programming"}


class PatchGovernanceCouncil:
    def decide(self, **kwargs: Any) -> Dict[str, Any]:
        return {"decision": "accept", "reason": "blueprint_loop_default_accept"}


class PatchApplier:
    def apply(self, patch_proposal: Any, sandbox: bool, mutable_only: bool) -> None:
        return


class MetricsSnapshotProvider:
    def snapshot(self) -> Dict[str, Any]:
        return {}


class ImmuneLoop:
    def build_snapshot(self) -> Dict[str, Any]:
        return {}

    def check_patch(self, patch: Any, report: Any) -> Dict[str, Any]:
        return {"status": "skipped"}


@dataclass
class BlueprintImprovementResult:
    section_id: str
    gap_kind: str
    patch_id: Optional[str]
    decision: str
    reason: str


class BlueprintImprovementLoop:
    def __init__(
        self,
        *,
        blueprint_store: Optional[BlueprintStore] = None,
        gap_tracker: Optional[BlueprintGapTracker] = None,
        self_prog: Optional[SelfProgrammingEngineV2] = None,
        patch_evaluator: Optional[PatchEvaluator] = None,
        patch_governance: Optional[PatchGovernanceCouncil] = None,
        patch_applier: Optional[PatchApplier] = None,
        metrics_provider: Optional[MetricsSnapshotProvider] = None,
        immune_loop: Optional[ImmuneLoop] = None,
        memory: Optional[Any] = None,
        objective_loader: Optional[ObjectiveLoader] = None,
        coverage_store: Optional[BlueprintCoverageStore] = None,
        objective_evaluator: Optional[BlueprintObjectiveEvaluator] = None,
    ) -> None:
        self.blueprint_store = blueprint_store or BlueprintStore()
        self.gap_tracker = gap_tracker or BlueprintGapTracker()
        self.self_prog = self_prog
        self.patch_evaluator = patch_evaluator or PatchEvaluator()
        self.patch_governance = patch_governance or PatchGovernanceCouncil()
        self.patch_applier = patch_applier or PatchApplier()
        self.metrics_provider = metrics_provider or MetricsSnapshotProvider()
        self.immune_loop = immune_loop or ImmuneLoop()
        self.memory = memory
        self.objective_loader = objective_loader or ObjectiveLoader()
        self.coverage_store = coverage_store or BlueprintCoverageStore()
        self.objective_evaluator = objective_evaluator or BlueprintObjectiveEvaluator()

        self.coverage_analyzer = BlueprintCoverageAnalyzer()

    def run(self, *, snapshot: Optional[Dict[str, Any]] = None, max_sections: int = 3) -> Dict[str, Any]:
        trace.record_event(
            new_trace_event(
                trace_id="blueprint-improvement",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "blueprint_improvement_start", "max_sections": max_sections},
            )
        )

        index = self.blueprint_store.load()
        coverage = self.coverage_analyzer.build_report(index, snapshot or {})
        try:
            self.coverage_store.save_current(coverage)
        except Exception:
            pass

        objectives = self.objective_loader.load()
        eval_result: Optional[ObjectiveEvalResult] = None
        try:
            eval_result = self.objective_evaluator.evaluate(coverage, objectives)
        except Exception:
            eval_result = None

        gaps = self.gap_tracker.find_gaps(coverage, objectives, limit=10)
        target_gaps = gaps[: max_sections or 0]

        results = [self._improve_single_section(g["section_id"], g) for g in target_gaps]
        improved_sections = [res.section_id for res in results if res.decision == "accept"]

        out = {
            "coverage_before": coverage.summary.to_dict(),
            "objective_eval": eval_result.global_status.__dict__ if eval_result and eval_result.global_status else None,
            "top_priority_sections": [p.__dict__ for p in (eval_result.section_priorities[:5] if eval_result else [])],
            "gaps_considered": target_gaps,
            "improvement_results": [r.__dict__ for r in results],
            "improved_sections": improved_sections,
        }

        trace.record_event(
            new_trace_event(
                trace_id="blueprint-improvement",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "blueprint_improvement_done", "result": out},
            )
        )
        return out

    def _improve_single_section(self, section_id: str, gap_data: Dict[str, Any]) -> BlueprintImprovementResult:
        gap = GapLike(
            id=section_id,
            title=f"Blueprint gap: {gap_data.get('kind')}",
            description=str(gap_data.get("description") or ""),
            category="blueprint_gap",
            priority=int(gap_data.get("severity", 1)),
            related_files=list(gap_data.get("suspect_files") or []),
            domain="blueprint",
        )

        # Delegate to self-programming if present.
        if self.self_prog is not None and hasattr(self.self_prog, "run_for_gaps"):
            try:
                self.self_prog.run_for_gaps([gap])
                return BlueprintImprovementResult(section_id, str(gap_data.get("kind") or ""), "delegated", "accept", "Delegated to SelfProgrammingEngineV2")
            except Exception as e:
                return BlueprintImprovementResult(section_id, str(gap_data.get("kind") or ""), None, "error", repr(e))

        return BlueprintImprovementResult(section_id, str(gap_data.get("kind") or ""), None, "skipped", "SelfProgrammingEngineV2 not attached")

