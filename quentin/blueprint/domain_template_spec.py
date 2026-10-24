from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class DomainTemplateSpec:
    """
    P11-B: Domain Template Specification
    Defines the standard requirements for a new domain.
    """
    domain_name: str
    required_modules: List[str] = field(default_factory=lambda: ["core", "security", "observability"])
    policy_defaults: Dict[str, Any] = field(default_factory=lambda: {
        "max_risk_level": "medium",
        "concurrency_limit": 5
    })
    safety_profile: str = "standard"
    rollout_strategy: str = "canary"
