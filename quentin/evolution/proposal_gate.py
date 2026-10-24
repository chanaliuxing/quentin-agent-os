from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from quentin.evolution.proposal_engine import Proposal
from quentin.governance.constitution import Constitution

@dataclass
class EvaluationResult:
    passed: bool
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

class ProposalGate:
    """
    P4-A: Evaluation Gate
    Dimensions: correctness, safety, perf/cost
    """
    def __init__(self, constitution: Optional[Constitution] = None) -> None:
        self.constitution = constitution or Constitution.load()

    def evaluate(self, proposal: Proposal, baseline_metrics: Optional[Dict[str, Any]] = None) -> EvaluationResult:
        # 1. Safety Check (Policy compliance)
        safety_res = self._check_safety(proposal)
        if not safety_res.passed:
            return safety_res

        # 2. Correctness Check
        correctness_res = self._check_correctness(proposal)
        if not correctness_res.passed:
            return correctness_res

        # 3. Performance/Cost Check
        if baseline_metrics:
            perf_res = self._check_performance(proposal, baseline_metrics)
            if not perf_res.passed:
                return perf_res

        return EvaluationResult(passed=True, reason="Proposal passed all gate checks.")

    def _check_safety(self, proposal: Proposal) -> EvaluationResult:
        # Check against auto_reject_for in constitution
        safety_config = self.constitution.get("safety", {})
        auto_reject = safety_config.get("auto_reject_for", [])
        
        # Simple mapping for demo purposes
        if "disable_safety_checks" in auto_reject and "safety" in proposal.target.lower():
             return EvaluationResult(passed=False, reason="Cannot modify safety systems via autonomous evolution.")

        # Check protected paths (if proposal targets specific files)
        protected_paths = self.constitution.get("protected_paths", [])
        for path in protected_paths:
            if path in proposal.target:
                return EvaluationResult(passed=False, reason=f"Target '{proposal.target}' contains protected path '{path}'.")

        if proposal.risk_level == "high":
            # High risk might need manual review
            return EvaluationResult(passed=False, reason="High risk proposal requires manual review.")
            
        return EvaluationResult(passed=True)

    def _check_correctness(self, proposal: Proposal) -> EvaluationResult:
        if not proposal.proposed_changes:
            return EvaluationResult(passed=False, reason="Proposal contains no changes.")
        
        if not proposal.rollback_plan:
             return EvaluationResult(passed=False, reason="Proposal is missing a rollback plan.")
             
        return EvaluationResult(passed=True)

    def _check_performance(self, proposal: Proposal, baseline: Dict[str, Any]) -> EvaluationResult:
        # Placeholder for A/B testing logic or heuristic-based prediction.
        return EvaluationResult(passed=True)
