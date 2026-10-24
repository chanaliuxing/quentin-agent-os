import pytest
from quentin.strategy.retrospective_evaluator import RetrospectiveEvaluator

def test_evaluator_pivot_recommendation():
    evaluator = RetrospectiveEvaluator()
    
    # Fail case: high regression / low completion
    roadmap_fail = {"completed_milestones": 1, "total_milestones": 5}
    trends_fail = {"success_rate": [0.4, 0.3, 0.2]}
    res_fail = evaluator.evaluate_period(roadmap_fail, trends_fail)
    assert res_fail["strategic_pivot_recommended"] is True
    
    # Success case
    roadmap_ok = {"completed_milestones": 4, "total_milestones": 5}
    trends_ok = {"success_rate": [0.9, 0.95, 0.98]}
    res_ok = evaluator.evaluate_period(roadmap_ok, trends_ok)
    assert res_ok["strategic_pivot_recommended"] is False
