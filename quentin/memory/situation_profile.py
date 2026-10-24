from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from quentin.memory.kinds import KIND_SITUATION_PROFILE
from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.utils.time import now_utc


def stable_situation_profile_id(situation_id: str) -> str:
    return f"situation_profile::{uuid.uuid5(uuid.NAMESPACE_URL, str(situation_id or ''))}"


@dataclass(frozen=True)
class SituationProfileEntry:
    """
    Memory protocol: kind=situation_profile

    Stored primarily in metadata to avoid hard DB schema coupling.
    """

    situation_id: str
    signals: List[str] = field(default_factory=list)
    recommended_skills: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "type": "SITUATION_PROFILE",
            "situation_id": self.situation_id,
            "signals": list(self.signals or []),
            "recommended_skills": list(self.recommended_skills or []),
            "stats": dict(self.stats or {}),
        }

    def to_memory_record(self, *, tier: MemoryTier = MemoryTier.MTS) -> MemoryRecord:
        now = now_utc()
        content = self.notes or f"SITUATION_PROFILE {self.situation_id}"
        return MemoryRecord(
            id=stable_situation_profile_id(self.situation_id),
            tier=tier,
            content=content,
            created_at=now,
            updated_at=now,
            source="sleep_loop",
            domain="cross",
            topic="situation_profile",
            importance=0.5,
            tags=["sleep", "situation_profile"],
            metadata=self.to_metadata(),
            consolidated_from_ids=[],
            supersedes_ids=[],
            kind=KIND_SITUATION_PROFILE,
            vector=None,
            relations={},
            update_policy=None,
            update_history=[],
        )

