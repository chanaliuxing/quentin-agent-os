from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from quentin.cognitive.perception.schemas import SituationAssessment, SkillInvocation


class SituationSkillRouter(Protocol):
    def route(self, *, situation: SituationAssessment, ctx: Dict[str, Any]) -> Optional[SkillInvocation]: ...


@dataclass
class MemoryBackedSituationSkillRouter:
    """
    v0 router: if memory has a situation_profile with recommended_skills, return the first.

    Safety:
    - legal/trading are blocked by default (caller should enforce too)
    """

    memory_fabric: Any
    min_confidence: float = 0.65

    def route(self, *, situation: SituationAssessment, ctx: Dict[str, Any]) -> Optional[SkillInvocation]:
        if situation.confidence < float(self.min_confidence):
            return None
        # Domain guard (default deny for high risk domains)
        domain = str(ctx.get("domain") or "").strip().lower()
        if domain in {"legal", "trading"}:
            return None

        try:
            from quentin.memory.models import MemoryQuery

            q = MemoryQuery(text=f"situation_id:{situation.situation_id}", kind="situation_profile", top_k=5)
            recs = self.memory_fabric.recall(q)
        except Exception:
            return None

        for r in recs or []:
            md = getattr(r, "metadata", None) or {}
            if str(md.get("situation_id") or "") != situation.situation_id:
                continue
            skills = md.get("recommended_skills")
            if isinstance(skills, list) and skills:
                skill_id = str(skills[0] or "").strip()
                if not skill_id:
                    continue
                return SkillInvocation(
                    skill_id=skill_id,
                    reason="situation_profile_recommended_skill",
                    min_confidence=float(self.min_confidence),
                    metadata={"situation_id": situation.situation_id},
                )
        return None

