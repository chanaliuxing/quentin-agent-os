from enum import Enum
from typing import List, Optional, Dict, Any

class SkillStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"

class SkillRegistry:
    """
    A simple SkillRegistry for the meta_agent layer.
    """
    def __init__(self):
        self._skills = {}

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self._skills.get(skill_id)

    def list_skills(self) -> List[Dict[str, Any]]:
        return list(self._skills.values())
    
    def register_skill(self, skill: Dict[str, Any]):
        skill_id = skill.get("skill_id")
        if skill_id:
            self._skills[skill_id] = skill
