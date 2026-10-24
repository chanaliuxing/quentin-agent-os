from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Principle:
    id: str
    text: str


@dataclass
class DomainGoal:
    id: str
    text: str


@dataclass
class CapabilityDoD:
    capability_name: str
    must_satisfy: List[str]


@dataclass
class Constitution:
    """
    Represent the AI system's Constitution, loaded from a YAML file.
    """
    global_principles: List[Principle] = field(default_factory=list)
    domains: Dict[str, Any] = field(default_factory=dict)
    definition_of_done: Dict[str, CapabilityDoD] = field(default_factory=dict)
    raw_spec: Dict[str, Any] = field(default_factory=dict) # To store raw yaml data

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "Constitution":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Constitution file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
        
        principles = [Principle(id=p['id'], text=p['text']) for p in raw_data.get('global_principles', [])]
        
        domains_data = raw_data.get('domains', {})
        
        dod_data = raw_data.get('definition_of_done', {})
        definition_of_done = {
            cap_name: CapabilityDoD(
                capability_name=cap_name,
                must_satisfy=dod_info
            )
            for cap_name, dod_info in dod_data.items()
        }

        return cls(
            global_principles=principles,
            domains=domains_data,
            definition_of_done=definition_of_done,
            raw_spec=raw_data
        )
