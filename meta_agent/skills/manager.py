# meta_agent/skills/manager.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from typing import Dict, List, Optional, Iterable
import datetime as dt

from meta_agent.skills.schema import (
    SkillDefinition,
    SkillStatus,
)
from meta_agent.skills.store import SkillStore


class SkillManager:
    def __init__(self, store: Optional[SkillStore] = None) -> None:
        self.store = store or SkillStore()
        self._skills: Dict[str, SkillDefinition] = self.store.load_all()

    def list_all(self, status: Optional[str] = None, domain: Optional[str] = None) -> List[SkillDefinition]:
        skills = list(self._skills.values())
        if status:
            skills = [s for s in skills if s.status == status]
        if domain:
            skills = [s for s in skills if s.domain == domain]
        return skills

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        return self._skills.get(skill_id)

    def register(self, skill: SkillDefinition) -> SkillDefinition:
        self._skills[skill.skill_id] = skill
        self._save()
        return skill

    def update_status(self, skill_id: str, status: str) -> None:
        skill = self._skills.get(skill_id)
        if not skill:
            return
        skill.status = status
        skill.updated_at = now_iso()
        self._save()

    def record_usage(self, skill_id: str, success: bool) -> None:
        skill = self._skills.get(skill_id)
        if not skill:
            return
        skill.stats.used_count += 1
        if success:
            skill.stats.success_count += 1
        skill.stats.last_used_at = now_iso()
        skill.updated_at = now_iso()
        self._save()

    def _save(self) -> None:
        self.store.save_all(self._skills)

    def find_applicable(
        self,
        *,
        domain: str,
        query: str,
        top_k: int = 5,
        status: str = SkillStatus.ACTIVE,
    ) -> List[SkillDefinition]:
        q = query.lower()
        candidates = [
            s for s in self._skills.values()
            if s.status == status and s.domain == domain
        ]

        def score(skill: SkillDefinition) -> int:
            score = 0
            text_fields = [skill.name] + skill.tags + [skill.description]
            for field in text_fields:
                if not field:
                    continue
                f = field.lower()
                if q in f:
                    score += 3
                for token in q.split():
                    if token and token in f:
                        score += 1
            return score

        ranked = sorted(candidates, key=score, reverse=True)
        return [s for s in ranked if score(s) > 0][:top_k]
