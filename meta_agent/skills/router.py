from typing import List, Dict, Any
from meta_agent.skills.registry import SkillRegistry

class SkillRouter:
    """
    A simple router to find skills relevant to a task.
    """
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def route(self, query: str, domain: str = None) -> List[Dict[str, Any]]:
        """
        Find skills that match the query.
        For now, just returns all skills in the registry.
        """
        return self.registry.list_skills()
