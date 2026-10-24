# meta_agent/skills/miner.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from meta_agent.memory.fabric import MemoryFabric, MemoryTier
from meta_agent.skills.schema import SkillDefinition, SkillImplType, SkillStatus
from meta_agent.skills.manager import SkillManager
from meta_agent.runtime import council
import asyncio


@dataclass
class MinedSkillCandidate:
    skill: SkillDefinition
    source_trace_ids: List[str]
    confidence: float
    reason: str


class SkillMiner:
    def __init__(
        self,
        memory: Optional[MemoryFabric] = None,
        skill_manager: Optional[SkillManager] = None,
    ) -> None:
        self.memory = memory or MemoryFabric()
        self.skill_manager = skill_manager or SkillManager()

    def mine_from_recent_traces(
        self,
        domain: str,
        max_traces: int = 50,
        min_success_repeats: int = 2,
    ) -> List[MinedSkillCandidate]:
        traces = self.memory.search(
            query=domain,
            tiers=[MemoryTier.STS, MemoryTier.MTS],
            kind="task_run",
            limit=max_traces,
        )

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for rec in traces:
            data = rec.metadata # Assuming payload is in metadata
            if not data.get("success"):
                continue
            if data.get("domain") != domain:
                continue
            task_type = data.get("task_type") or "unknown"
            groups.setdefault(task_type, []).append(data)

        candidates: List[MinedSkillCandidate] = []
        for task_type, items in groups.items():
            if len(items) < min_success_repeats:
                continue

            ctx = {"domain": domain, "task_type": task_type, "examples": items[:5]}
            schema_hint = """
            Output JSON with keys: "name", "tags", "description", "signature", "impl_type",
            "impl_payload", "confidence", "reason".
            """
            question = f"Summarize a reusable skill definition from these successful '{domain}/{task_type}' tasks."

            try:
                res = council.ask_json(role="skill_mining", question=question, context=ctx, json_schema_hint=schema_hint)
                if hasattr(res, "__await__"):
                    res = asyncio.run(res)  # type: ignore[assignment]
            except Exception:
                continue

            try:
                skill = SkillDefinition.new(
                    name=res.get("name", f"{domain}-{task_type}-skill"),
                    domain=domain,
                    tags=list(res.get("tags") or []),
                    description=res.get("description", ""),
                    signature=res.get("signature") or {},
                    impl_type=res.get("impl_type", SkillImplType.LLM_PROMPT),
                    impl_payload=res.get("impl_payload") or {},
                    status=SkillStatus.CANDIDATE,
                )
                candidate = MinedSkillCandidate(
                    skill=skill,
                    source_trace_ids=[d.get("trace_id", "") for d in items],
                    confidence=float(res.get("confidence", 0.5)),
                    reason=res.get("reason", ""),
                )
                candidates.append(candidate)
            except Exception:
                continue

        return candidates

    def promote_candidates(
        self,
        candidates: List[MinedSkillCandidate],
        min_confidence: float = 0.6,
    ) -> List[SkillDefinition]:
        promoted: List[SkillDefinition] = []
        for c in candidates:
            skill = c.skill
            if c.confidence >= min_confidence:
                skill.status = SkillStatus.ACTIVE
            self.skill_manager.register(skill)
            promoted.append(skill)
        return promoted
