# meta_agent/skills/store.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
import json

from meta_agent.skills.schema import SkillDefinition


class SkillStore:
    def __init__(self, path: str | Path = "data/skills/skills.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> Dict[str, SkillDefinition]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = {}
            for item in raw.get("skills", []):
                skill = SkillDefinition.from_dict(item)
                items[skill.skill_id] = skill
            return items
        except (json.JSONDecodeError, TypeError):
            return {}

    def save_all(self, skills: Dict[str, SkillDefinition]) -> None:
        data = {"skills": [s.to_dict() for s in skills.values()]}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
