from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time

@dataclass
class TowerSnapshot:
    timestamp: float
    health_status: str
    slo_status: Dict[str, Any]
    pending_approvals: int
    active_releases: List[str]
    federation_summary: Dict[str, Any]
    active_risks: List[Dict[str, Any]]

class OperationsControlTower:
    """
    P11-A: Operations Control Tower
    Aggregates global system state for monitoring and risk management.
    """
    def __init__(
        self,
        error_budget: Optional[Any] = None,
        approval_chain: Optional[Any] = None,
        node_registry: Optional[Any] = None
    ) -> None:
        self.error_budget = error_budget
        self.approval_chain = approval_chain
        self.node_registry = node_registry

    def get_overview(self) -> TowerSnapshot:
        # Mocking values if dependencies aren't injected for demo
        slo_data = {}
        if hasattr(self.error_budget, "budgets"):
            for name, b in self.error_budget.budgets.items():
                slo_data[name] = {"remaining": b.remaining_budget, "is_exhausted": b.is_exhausted}
        
        pending_count = 0
        if hasattr(self.approval_chain, "requests"):
            pending_count = len([r for r in self.approval_chain.requests.values() if r.status == "pending"])

        nodes_count = 0
        if hasattr(self.node_registry, "nodes"):
            nodes_count = len(self.node_registry.nodes)

        return TowerSnapshot(
            timestamp=time.time(),
            health_status="degraded" if any(b.get("is_exhausted") for b in slo_data.values()) else "healthy",
            slo_status=slo_data,
            pending_approvals=pending_count,
            active_releases=[], # placeholder
            federation_summary={"total_nodes": nodes_count},
            active_risks=self._identify_risks(slo_data, pending_count)
        )

    def _identify_risks(self, slo_data: Dict[str, Any], pending_approvals: int) -> List[Dict[str, Any]]:
        risks = []
        for name, data in slo_data.items():
            if data["is_exhausted"]:
                risks.append({"id": f"slo_exhausted_{name}", "severity": "high", "description": f"SLO {name} budget exhausted"})
        
        if pending_approvals > 5:
            risks.append({"id": "approval_backlog", "severity": "medium", "description": "High number of pending approvals"})
            
        return risks

    def get_incidents(self) -> List[Dict[str, Any]]:
        """
        P11-A: Fetch active or recent incidents.
        """
        # Mocking incidents for now
        return [
            {
                "id": "INC-001",
                "type": "slo_violation",
                "status": "investigating",
                "timestamp": time.time() - 3600,
                "description": "High latency detected in core domain"
            }
        ]
