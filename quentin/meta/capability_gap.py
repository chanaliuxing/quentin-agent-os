from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
import uuid

from quentin.utils.time import now_utc_iso


@dataclass(frozen=True)
class CapabilityGapEvidence:
    type: str  # e.g. "tool_error", "trace_event"
    ref: str   # trace_id / tool_call_id / etc
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityGap:
    """
    A normalized representation of a missing capability.

    This object is intended to be stable and pluggable so that:
    - DualTrackRouter can route it (MCP vs self-programming)
    - Governance can gate the chosen action
    - Memory can store it for later consolidation
    """

    gap_id: str
    gap_type: str  # "tool_not_found" | "tool_blocked" | "tool_failed" | "missing_skill" | ...
    gap_text: str
    domain: str
    environment: str
    tool_name: Optional[str] = None
    suggested_track: Optional[str] = None  # "mcp" | "self_programming"
    evidence: List[CapabilityGapEvidence] = field(default_factory=list)
    created_at: str = field(default_factory=now_utc_iso)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        *,
        gap_type: str,
        gap_text: str,
        domain: str,
        environment: str,
        tool_name: Optional[str] = None,
        suggested_track: Optional[str] = None,
        evidence: Optional[List[CapabilityGapEvidence]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "CapabilityGap":
        return cls(
            gap_id=f"gap_{uuid.uuid4().hex}",
            gap_type=str(gap_type or "").strip() or "unknown",
            gap_text=str(gap_text or "").strip(),
            domain=str(domain or "core"),
            environment=str(environment or "sandbox"),
            tool_name=(str(tool_name).strip() if tool_name else None),
            suggested_track=(str(suggested_track).strip() if suggested_track else None),
            evidence=list(evidence or []),
            meta=dict(meta or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type,
            "gap_text": self.gap_text,
            "domain": self.domain,
            "environment": self.environment,
            "tool_name": self.tool_name,
            "suggested_track": self.suggested_track,
            "evidence": [e.to_dict() for e in (self.evidence or [])],
            "created_at": self.created_at,
            "meta": dict(self.meta or {}),
        }

