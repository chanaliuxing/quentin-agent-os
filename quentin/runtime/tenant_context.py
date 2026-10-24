from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class TenantContext:
    """
    P4-B: Tenant Context Model
    Represents the context of a specific tenant and session.
    Used for resource isolation and quota management.
    """
    tenant_id: str
    session_id: str
    domain: str = "general"
    risk_profile: str = "standard" # "standard", "high_risk", "low_risk"
    budget_profile: str = "standard" # "standard", "economy", "premium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "domain": self.domain,
            "risk_profile": self.risk_profile,
            "budget_profile": self.budget_profile,
            **self.metadata
        }
