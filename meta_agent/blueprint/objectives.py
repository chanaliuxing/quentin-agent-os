# meta_agent/blueprint/objectives.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional
from pathlib import Path
import json
import datetime as dt


@dataclass
class SectionObjective:
    section_id: str
    target_level: str
    target_date: Optional[str]
    weight: float = 1.0
    notes: str = ""


@dataclass
class GlobalObjective:
    target_self_evolving_sections: int
    target_date: Optional[str] = None
    notes: str = ""


@dataclass
class BlueprintObjectives:
    global_obj: Optional[GlobalObjective]
    sections: Dict[str, SectionObjective]


class ObjectiveLoader:
    def __init__(self, path: str | Path = "data/blueprint/objectives.json") -> None:
        self.path = Path(path)

    def load(self) -> BlueprintObjectives:
        if not self.path.exists():
            return BlueprintObjectives(global_obj=None, sections={})

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        g = raw.get("global")
        if g:
            global_obj = GlobalObjective(
                target_self_evolving_sections=int(g.get("target_self_evolving_sections", 0)),
                target_date=g.get("target_date"),
                notes=g.get("notes", ""),
            )
        else:
            global_obj = None

        sections: Dict[str, SectionObjective] = {}
        for sec_id, cfg in (raw.get("sections") or {}).items():
            sections[sec_id] = SectionObjective(
                section_id=sec_id,
                target_level=cfg.get("target_level", "implemented"),
                target_date=cfg.get("target_date"),
                weight=float(cfg.get("weight", 1.0)),
                notes=cfg.get("notes", ""),
            )

        return BlueprintObjectives(global_obj=global_obj, sections=sections)
