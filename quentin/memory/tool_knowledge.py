from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.memory.kinds import KIND_TOOL_KNOWLEDGE
from quentin.utils.time import now_utc


def stable_tool_knowledge_id(tool_name: str) -> str:
    return f"tool_knowledge::{uuid.uuid5(uuid.NAMESPACE_URL, str(tool_name or ''))}"


@dataclass
class ToolKnowledgeEntry:
    tool_name: str
    signature: str = ""
    description: str = ""
    examples: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    tags: List[str] = field(default_factory=list)
    governance_state: str = "experimental"  # experimental|trusted|deprecated
    notes: Optional[str] = None

    def to_memory_record(self, *, tier: MemoryTier = MemoryTier.LTS) -> MemoryRecord:
        now = now_utc()
        rec = MemoryRecord(
            id=stable_tool_knowledge_id(self.tool_name),
            tier=tier,
            content=(self.notes or self.description or self.signature or self.tool_name),
            created_at=now,
            updated_at=now,
            source="tool_manager",
            domain="cross",
            topic="tool_knowledge",
            importance=0.7,
            tags=list(self.tags or []),
            metadata={
                "tool_name": self.tool_name,
                "signature": self.signature,
                "description": self.description,
                "examples": list(self.examples or []),
                "stats": dict(self.stats or {}),
                "risk_level": self.risk_level,
                "governance_state": self.governance_state,
            },
            consolidated_from_ids=[],
            supersedes_ids=[],
            kind=KIND_TOOL_KNOWLEDGE,
            vector=None,
            relations={},
            update_policy=None,
            update_history=[],
        )
        return rec

