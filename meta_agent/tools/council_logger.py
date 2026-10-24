# meta_agent/tools/council_logger.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from meta_agent.memory.fabric import MemoryFabric
from meta_agent.memory.types import MemoryRecord, MemoryTier


@dataclass
class CouncilVote:
    role: str
    decision: str
    rationale: str
    constraints: str | None = None


def log_council_votes(
    memory_fabric: MemoryFabric,
    *,
    proposal_id: str,
    tool_id: str,
    target_state: str,
    votes: List[Dict[str, Any]],
    approved: bool,
    transcripts: Optional[Dict[str, str]] = None,
) -> None:
    text = f"Council votes for {tool_id} -> {target_state}: {'approved' if approved else 'rejected'}"
    rec = MemoryRecord.new(
        text=text,
        tier=MemoryTier.MTS,
        kind="council_vote",
        metadata={
            "proposal_id": proposal_id,
            "tool_id": tool_id,
            "target_state": target_state,
            "approved": approved,
            "votes": votes,
            "transcripts": transcripts or {},
        },
        importance=0.7,
    )
    memory_fabric.store.upsert(rec)
