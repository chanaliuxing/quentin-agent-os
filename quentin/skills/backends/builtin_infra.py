from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from .base import SkillBackend
from quentin.infra.skills_provider import BuiltinSkillProvider

logger = logging.getLogger(__name__)

class BuiltinInfraSkillBackend(SkillBackend):
    """
    Exposes hardcoded infra skills (Browser, Mobile, Desktop)
    to the SkillManager without requiring external JSON/MD files.
    """
    def __init__(self, priority: int = 200):
        super().__init__(priority=priority)
        self._skills = {s["skill_id"]: s for s in BuiltinSkillProvider.get_definitions()}

    def list_skills(self, domain: str | None = None) -> List[Dict[str, Any]]:
        # Filter by domain if needed (e.g. mobile.* -> mobile domain)
        return list(self._skills.values())

    def load_exec_callable(self, skill_id: str) -> Tuple[Optional[Callable], Any]:
        if skill_id in self._skills:
            # We wrap the provider's execute in a compatible signature
            async def _wrapper(step, goal, context):
                return await BuiltinSkillProvider.execute(skill_id, step.get("args", {}))
            return _wrapper, None
        return None, None

    def load_sop_text(self, skill_id: str) -> Optional[str]:
        return None # Builtin skills are pure code, no SOP needed
