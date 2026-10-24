from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

@dataclass
class Proposal:
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target: str = ""  # e.g., "routing_policy", "compaction_strategy"
    change_type: str = "" # e.g., "tuning", "structural", "feature_enable"
    description: str = ""
    impact_scope: List[str] = field(default_factory=list)
    risk_level: str = "medium"  # "low", "medium", "high"
    proposed_changes: Dict[str, Any] = field(default_factory=dict)
    rollback_plan: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "proposed" # "proposed", "evaluating", "accepted", "rejected", "applied", "rolled_back"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ProposalEngine:
    """
    P4-A: Proposal Engine
    Inputs: running metrics, failure modes, gap signals
    Outputs: structured proposals
    """
    def __init__(self) -> None:
        pass

    def generate_proposals(
        self, 
        metrics: Optional[Dict[str, Any]] = None, 
        failures: Optional[List[Dict[str, Any]]] = None,
        gaps: Optional[List[str]] = None
    ) -> List[Proposal]:
        proposals: List[Proposal] = []
        
        if metrics:
            proposals.extend(self._analyze_metrics(metrics))
        
        if failures:
            proposals.extend(self._analyze_failures(failures))
            
        if gaps:
            proposals.extend(self._analyze_gaps(gaps))
            
        return proposals

    def _analyze_metrics(self, metrics: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        # Example: If latency is high, propose switching to a faster model
        avg_latency = metrics.get("avg_latency_ms")
        if avg_latency and avg_latency > 5000:
            proposals.append(Proposal(
                target="routing_policy",
                change_type="tuning",
                description="High average latency detected. Proposing switch to faster models for general tasks.",
                impact_scope=["routing"],
                risk_level="low",
                proposed_changes={"preference": "speed"},
                rollback_plan="Revert routing preference to 'balanced'."
            ))
        return proposals

    def _analyze_failures(self, failures: List[Dict[str, Any]]) -> List[Proposal]:
        proposals = []
        # Example: If many rate limit errors, propose adding a retry delay or switching provider
        rate_limit_failures = [f for f in failures if "rate_limit" in str(f.get("error", "")).lower()]
        if len(rate_limit_failures) > 5:
            proposals.append(Proposal(
                target="infra_config",
                change_type="tuning",
                description="Frequent rate limits detected. Proposing increased retry backoff.",
                impact_scope=["infra", "reliability"],
                risk_level="low",
                proposed_changes={"retry_backoff_factor": 2.0},
                rollback_plan="Restore default retry backoff."
            ))
        return proposals

    def _analyze_gaps(self, gaps: List[str]) -> List[Proposal]:
        proposals = []
        for gap in gaps:
            if "memory_bottleneck" in gap:
                proposals.append(Proposal(
                    target="memory_policy",
                    change_type="tuning",
                    description="Memory bottleneck signal received. Proposing more aggressive compaction.",
                    impact_scope=["memory"],
                    risk_level="medium",
                    proposed_changes={"compaction_threshold": 0.5},
                    rollback_plan="Restore default compaction threshold."
                ))
        return proposals
