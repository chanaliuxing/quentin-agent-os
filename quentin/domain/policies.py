from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DomainPolicy:
    domain: str
    model_whitelist: List[str] = field(default_factory=list)
    max_risk_level: str = "medium"
    allow_self_programming: bool = False
    mutable_allow_roots: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_DOMAIN_POLICIES: Dict[str, DomainPolicy] = {
    "core": DomainPolicy(domain="core", model_whitelist=[], max_risk_level="high", allow_self_programming=True, mutable_allow_roots=["mutable/"]),
    "desktop": DomainPolicy(domain="desktop", model_whitelist=[], max_risk_level="high", allow_self_programming=True, mutable_allow_roots=["mutable/"]),
    "legal": DomainPolicy(domain="legal", model_whitelist=[], max_risk_level="medium", allow_self_programming=False, mutable_allow_roots=["mutable/"]),
    "trading": DomainPolicy(domain="trading", model_whitelist=[], max_risk_level="medium", allow_self_programming=False, mutable_allow_roots=["mutable/"]),
    "cross": DomainPolicy(domain="cross", model_whitelist=[], max_risk_level="medium", allow_self_programming=False, mutable_allow_roots=["mutable/"]),
}


def get_domain_policy(domain: str) -> DomainPolicy:
    key = (domain or "core").strip().lower()
    return DEFAULT_DOMAIN_POLICIES.get(key) or DEFAULT_DOMAIN_POLICIES["core"]

