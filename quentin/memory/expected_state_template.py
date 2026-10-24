from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from quentin.memory.kinds import KIND_EXPECTED_STATE_TEMPLATE
from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.utils.time import now_utc


def stable_expected_state_template_id(situation_id: str) -> str:
    return f"expected_state_template::{uuid.uuid5(uuid.NAMESPACE_URL, str(situation_id or ''))}"


@dataclass(frozen=True)
class ExpectedStateTemplateEntry:
    """
    Memory protocol: kind=expected_state_template
    """

    situation_id: str
    expected_markers: List[str] = field(default_factory=list)
    fallback_paths: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "type": "EXPECTED_STATE_TEMPLATE",
            "situation_id": self.situation_id,
            "expected_markers": list(self.expected_markers or []),
            "fallback_paths": list(self.fallback_paths or []),
            "stats": dict(self.stats or {}),
        }

    def to_memory_record(self, *, tier: MemoryTier = MemoryTier.MTS) -> MemoryRecord:
        now = now_utc()
        content = self.notes or f"EXPECTED_STATE_TEMPLATE {self.situation_id}"
        return MemoryRecord(
            id=stable_expected_state_template_id(self.situation_id),
            tier=tier,
            content=content,
            created_at=now,
            updated_at=now,
            source="sleep_loop",
            domain="cross",
            topic="expected_state_template",
            importance=0.4,
            tags=["sleep", "expected_state_template"],
            metadata=self.to_metadata(),
            consolidated_from_ids=[],
            supersedes_ids=[],
            kind=KIND_EXPECTED_STATE_TEMPLATE,
            vector=None,
            relations={},
            update_policy=None,
            update_history=[],
        )

