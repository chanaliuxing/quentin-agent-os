import json
from quentin.evolution.roadmap_manager import RoadmapManager, Milestone

def main():
    manager = RoadmapManager()
    manager.add_milestone(Milestone("M1", "Enable multi-tenant isolation", "2026-03-01", "completed", 2.0))
    manager.add_milestone(Milestone("M2", "Scale to 100 federated nodes", "2026-06-01", "active", 3.0))
    
    report = {
        "summary": "Roadmap Alignment Report",
        "milestones": [m.__dict__ for m in manager.milestones.values()],
        "completion_rate": len([m for m in manager.milestones.values() if m.status == "completed"]) / len(manager.milestones)
    }
    
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
