import json
from quentin.strategy.retrospective_evaluator import RetrospectiveEvaluator

def main():
    evaluator = RetrospectiveEvaluator()
    
    # Mock data for Q1 2026
    roadmap = {"completed_milestones": 4, "total_milestones": 5}
    trends = {"success_rate": [0.95, 0.96, 0.97]}
    
    report = evaluator.evaluate_period(roadmap, trends)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
