# meta_agent/blueprint/self_update_engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import os

from meta_agent.blueprint.patch_models import (
    BlueprintPatchProposal,
    BlueprintPatchOperation,
)
from meta_agent.blueprint.gap_tracker_v2 import BlueprintGapTrackerV2, BlueprintGap
from meta_agent.monitoring.status_snapshot import build_status_snapshot
from quentin.traces.core import JsonlTraceRecorder

from meta_agent.blueprint.self_update_safety import BlueprintPatchSafetyChecker
from meta_agent.blueprint.self_update_applier import BlueprintPatchApplier

from quentin.traces.core import TraceEventType, new_trace_event


class PatchGovernanceCouncil:
    """
    Minimal deterministic governance for blueprint patch proposals.

    Policy:
    - If `requires_human_approval=True` OR risk_level != low -> do not auto apply.
    - Otherwise allow auto apply (subject to engine config flags).
    """

    def decide_on_blueprint_patch(self, proposal: BlueprintPatchProposal) -> "Decision":
        allow = (not proposal.requires_human_approval) and str(proposal.risk_level or "") == "low"

        class Decision:
            should_apply = bool(allow)

            def __init__(self, should_apply: bool, reason: str) -> None:
                self.should_apply = should_apply
                self.reason = reason

            def to_dict(self) -> Dict[str, Any]:
                return {"should_apply": bool(self.should_apply), "reason": str(self.reason)}

        if allow:
            return Decision(True, "low_risk_auto_apply_allowed")
        if proposal.requires_human_approval:
            return Decision(False, "requires_human_approval")
        return Decision(False, f"risk_level={proposal.risk_level}")

# --- Main Skeleton from 17.md ---

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class BlueprintSelfUpdateConfig:
    blueprint_path: str = "blueprint/blueprint_v2.yml"
    project_root: str = "."
    max_operations_per_patch: int = 10
    max_patches_per_cycle: int = 1
    allow_auto_apply: bool = False

class BlueprintSelfUpdateEngine:
    def __init__(
        self,
        config: Optional[BlueprintSelfUpdateConfig] = None,
        council: Optional[PatchGovernanceCouncil] = None,
        safety_checker: Optional[BlueprintPatchSafetyChecker] = None,
        applier: Optional[BlueprintPatchApplier] = None,
    ) -> None:
        self.config = config or BlueprintSelfUpdateConfig()
        self._gap_tracker = BlueprintGapTrackerV2(blueprint_path=self.config.blueprint_path, project_root=self.config.project_root)
        self._council = council or PatchGovernanceCouncil()
        self._safety_checker = safety_checker or BlueprintPatchSafetyChecker()
        self._applier = applier or BlueprintPatchApplier(blueprint_path=self.config.blueprint_path)

    def run_cycle(self) -> None:
        trace.record_event(new_trace_event(
            trace_id="bp_self_update",
            event_type=TraceEventType.DECISION,
            payload={"action": "bp_self_update_cycle_start", "blueprint_path": self.config.blueprint_path},
        ))
        snapshot = build_status_snapshot(window_hours=24)
        gaps = self._gap_tracker.collect_all_gaps(with_quality=True)
        proposals = self._propose_blueprint_patches(gaps=gaps, snapshot=snapshot, max_patches=self.config.max_patches_per_cycle)
        for proposal in proposals:
            self._process_single_proposal(proposal)
        trace.record_event(new_trace_event(
            trace_id="bp_self_update",
            event_type=TraceEventType.DECISION,
            payload={"action": "bp_self_update_cycle_done", "num_proposals": len(proposals)},
        ))

    def _propose_blueprint_patches(self, gaps: List[BlueprintGap], snapshot, max_patches: int) -> List[BlueprintPatchProposal]:
        top_gaps = self._gap_tracker.find_top_gaps(limit=10)
        prompt = self._build_blueprint_update_prompt(gaps=top_gaps, snapshot=snapshot)
        raw = self._council_chat(system="You are an architect council...", user=prompt)
        proposals = self._parse_patch_proposals_from_json(raw)
        return proposals[:max_patches]

    def _build_blueprint_update_prompt(self, gaps: List[BlueprintGap], snapshot) -> str:
        gap_summaries = [{"id": g.id, "title": g.title, "quality": g.quality.to_dict() if g.quality else None} for g in gaps]
        snapshot_brief = {"tasks_total": snapshot.task_stats_overall.total, "fail_rate": snapshot.task_stats_overall.fail_rate}
        return f"Gaps:\n{json.dumps(gap_summaries, indent=2)}\nSnapshot:\n{json.dumps(snapshot_brief, indent=2)}\n\nPlease propose blueprint updates in JSON format."

    def _parse_patch_proposals_from_json(self, raw: str) -> List[BlueprintPatchProposal]:
        proposals: List[BlueprintPatchProposal] = []
        try:
            data = json.loads(raw)
            if not isinstance(data, list): return []
            for item in data:
                ops = [BlueprintPatchOperation(**op) for op in item.get("operations", [])]
                prop = BlueprintPatchProposal.new(title=item.get("title", ""), description=item.get("description", ""), operations=ops)
                prop.risk_level = item.get("risk_level", "medium")
                prop.requires_human_approval = bool(item.get("requires_human_approval", False))
                proposals.append(prop)
        except Exception:
            trace.record_event(new_trace_event(
                trace_id="bp_self_update",
                event_type=TraceEventType.ERROR,
                payload={"action": "bp_self_update_parse_error", "raw_preview": raw[:1000]},
            ))
        return proposals

    def _process_single_proposal(self, proposal: BlueprintPatchProposal) -> None:
        trace.record_event(new_trace_event(
            trace_id=proposal.id,
            event_type=TraceEventType.DECISION,
            payload={"action": "bp_self_update_proposal_received", "proposal": proposal.to_dict()},
        ))
        safety_result = self._safety_checker.check_proposal(proposal)
        if safety_result.is_blocked:
            trace.record_event(new_trace_event(
                trace_id=proposal.id,
                event_type=TraceEventType.DECISION,
                payload={"action": "bp_self_update_blocked_by_safety", "reasons": safety_result.reasons},
            ))
            return

        decision = self._council.decide_on_blueprint_patch(proposal)
        trace.record_event(new_trace_event(
            trace_id=proposal.id,
            event_type=TraceEventType.DECISION,
            payload={"action": "bp_self_update_governance_decision", "decision": decision.to_dict()},
        ))

        if not decision.should_apply: return
        if not self.config.allow_auto_apply or proposal.requires_human_approval:
            trace.record_event(new_trace_event(
                trace_id=proposal.id,
                event_type=TraceEventType.DECISION,
                payload={"action": "bp_self_update_not_applied_due_to_policy"},
            ))
            return

        apply_result = self._applier.apply_proposal(proposal)
        if apply_result.is_blocked:
            trace.record_event(new_trace_event(
                trace_id=proposal.id,
                event_type=TraceEventType.DECISION,
                payload={"action": "bp_self_update_applier_blocked", "reasons": apply_result.reasons},
            ))
            return
            
        trace.record_event(new_trace_event(
            trace_id=proposal.id,
            event_type=TraceEventType.DECISION,
            payload={"action": "bp_self_update_applied", "modified_clauses": apply_result.modified_clause_ids},
        ))

    def _council_chat(self, system: str, user: str) -> str:
        """
        LLM-backed proposal generator, feature-flagged.

        Zero-config default: disabled (returns "[]") to avoid unexpected blueprint mutations.
        """
        enabled = os.environ.get("META_AGENT_ENABLE_BLUEPRINT_SELF_UPDATE_LLM", "").strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return "[]"

        try:
            from meta_agent.runtime import council

            res = council.ask_json(
                role="blueprint_self_update",
                question=user,
                context={"system": system},
                json_schema_hint="Return a JSON array of patch proposals, each with title, description, risk_level, requires_human_approval, operations[].",
            )
            if hasattr(res, "__await__"):
                import asyncio

                res = asyncio.run(res)  # type: ignore[assignment]
            return json.dumps(res, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            trace.record_event(new_trace_event(
                trace_id="bp_self_update",
                event_type=TraceEventType.ERROR,
                payload={"action": "bp_self_update_llm_error", "error": repr(e)},
            ))
            return "[]"
