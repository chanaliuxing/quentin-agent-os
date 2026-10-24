from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

@dataclass
class Milestone:
    id: str
    goal: str
    target_date: str
    status: str = "planned" # "planned", "active", "completed", "blocked"
    impact_factor: float = 1.0

class RoadmapManager:
    """
    P8-A: Evolution Roadmap Manager
    Tracks long-term goals and milestones for autonomous evolution.
    """
    def __init__(self) -> None:
        self.milestones: Dict[str, Milestone] = {}

    def add_milestone(self, milestone: Milestone) -> None:
        self.milestones[milestone.id] = milestone

    def update_status(self, milestone_id: str, status: str) -> bool:
        if milestone_id in self.milestones:
            self.milestones[milestone_id].status = status
            return True
        return False

    def get_active_roadmap(self) -> List[Milestone]:
        return [m for m in self.milestones.values() if m.status in ("planned", "active")]
