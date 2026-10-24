from __future__ import annotations
from typing import List, Dict, Any
from quentin.evolution.roadmap_manager import RoadmapManager, Milestone

class RoadmapScheduler:
    """
    P8-A: Evolution Task Scheduler
    Prioritizes evolution tasks based on roadmap goals, risk, and potential gain.
    """
    def __init__(self, roadmap: RoadmapManager) -> None:
        self.roadmap = roadmap

    def schedule_tasks(self, available_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort tasks by priority score.
        Score = (Impact * Roadmap_Alignment) / Risk
        """
        active_goals = self.roadmap.get_active_roadmap()
        
        scored_tasks = []
        for task in available_tasks:
            alignment = 1.0
            for goal in active_goals:
                if goal.goal.lower() in task.get("description", "").lower():
                    alignment += goal.impact_factor
            
            risk = task.get("risk_score", 1.0)
            impact = task.get("potential_gain", 1.0)
            
            score = (impact * alignment) / risk
            task["priority_score"] = score
            scored_tasks.append(task)
            
        return sorted(scored_tasks, key=lambda x: x["priority_score"], reverse=True)
