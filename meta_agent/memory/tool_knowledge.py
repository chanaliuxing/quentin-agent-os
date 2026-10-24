# meta_agent/memory/tool_knowledge.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from meta_agent.memory.types import MemoryRecord, MemoryTier

TOOL_KNOWLEDGE_KIND = "tool_knowledge"


@dataclass
class ToolKnowledge:
    tool_id: str
    server: str
    signature: str
    description: str
    examples: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    governance: Dict[str, Any] = field(default_factory=dict)
    transport: Optional[str] = None
    uri: Optional[str] = None
    notes: Optional[str] = None

    def to_memory_record(self, tier: MemoryTier = MemoryTier.LTS, record_id: Optional[str] = None) -> MemoryRecord:
        """
        Render this tool knowledge entry into a MemoryRecord so it can be indexed
        alongside other long-term knowledge.
        """
        text = self.notes or self.description
        metadata = {
            "tool_id": self.tool_id,
            "server": self.server,
            "transport": self.transport,
            "uri": self.uri,
            "signature": self.signature,
            "description": self.description,
            "examples": self.examples,
            "metrics": self.metrics,
            "governance": self.governance,
        }
        rec = MemoryRecord.new(
            text=text,
            tier=tier,
            kind=TOOL_KNOWLEDGE_KIND,
            metadata=metadata,
            importance=0.7,
        )
        if record_id:
            rec.id = record_id
        return rec
