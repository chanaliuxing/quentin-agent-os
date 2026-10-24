from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Evidence:
    source: str       # e.g., "ast", "config", "test", "file_system"
    key: str          # e.g., "class_found", "file_missing", "todo_detected"
    score: float      # contribution to confidence (can be negative)
    details: str      # human-readable detail


@dataclass
class RequirementStatus:
    req_id: str
    title: str
    status: str       # "implemented", "partial", "unknown", "gap"
    confidence: float # 0.0 - 1.0
    evidence_chain: List[Evidence] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        # stable ordering of evidence for deterministic outputs
        ordered = sorted(
            self.evidence_chain,
            key=lambda e: (e.source, e.key, e.details)
        )
        return {
            "req_id": self.req_id,
            "title": self.title,
            "status": self.status,
            "confidence": round(self.confidence, 2),
            "evidence": [
                {"src": e.source, "key": e.key, "score": e.score, "msg": e.details}
                for e in ordered
            ],
            "missing": self.missing_items,
        }
