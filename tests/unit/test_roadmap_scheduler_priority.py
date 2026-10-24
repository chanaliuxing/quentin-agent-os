import pytest
from quentin.evolution.roadmap_manager import RoadmapManager, Milestone
from quentin.evolution.roadmap_scheduler import RoadmapScheduler

def test_roadmap_priority_scheduling():
    manager = RoadmapManager()
    manager.add_milestone(Milestone("M1", "Auto-scaling", "2026", "active", 2.0))
    
    scheduler = RoadmapScheduler(manager)
    
    tasks = [
        {"description": "Generic task", "risk_score": 1.0, "potential_gain": 1.0},
        {"description": "Task for Auto-scaling", "risk_score": 1.0, "potential_gain": 1.0},
    ]
    
    scheduled = scheduler.schedule_tasks(tasks)
    
    assert scheduled[0]["description"] == "Task for Auto-scaling"
    assert scheduled[0]["priority_score"] > scheduled[1]["priority_score"]
