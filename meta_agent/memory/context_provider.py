# meta_agent/memory/context_provider.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from meta_agent.memory.fabric import MemoryFabric
from meta_agent.memory.types import MemoryTier, MemoryRecord


@dataclass
class MemoryContext:
    semantic: List[MemoryRecord]
    observations: List[MemoryRecord]

    def to_prompt_block(self) -> str:
        lines = []
        if self.semantic:
            lines.append("【长期/语义记忆（MTS/LTS）】")
            for rec in self.semantic[:8]:
                lines.append(f"- ({rec.kind}, imp={rec.importance:.2f}) {rec.text}")
        if self.observations:
            lines.append("\n【近期观察（STS）】")
            for rec in self.observations[:8]:
                lines.append(f"- {rec.text}")
        return "\n".join(lines)


class MemoryContextProvider:
    def __init__(self, fabric: Optional[MemoryFabric] = None) -> None:
        self.fabric = fabric or MemoryFabric()

    def build_for_task(self, task: Dict[str, Any]) -> MemoryContext:
        goal = task.get("goal") or task.get("description") or ""
        ttype = task.get("type") or ""
        domain = task.get("domain") or ""

        query_parts = [goal, ttype, domain]
        query = " ".join(p for p in query_parts if p).strip()
        if not query: query = "general"

        semantic = self.fabric.search(query=query, tiers=[MemoryTier.MTS, MemoryTier.LTS], kind="semantic", limit=10)
        observations = self.fabric.search(query=query, tiers=[MemoryTier.STS], kind="observation", limit=10)
        return MemoryContext(semantic=semantic, observations=observations)
