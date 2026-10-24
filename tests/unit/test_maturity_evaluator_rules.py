import pytest
from quentin.certification.maturity_evaluator import MaturityEvaluator, MaturityLevel

def test_maturity_evaluation_logic():
    evaluator = MaturityEvaluator()
    
    # High score -> High maturity
    metrics = {"safety_false_positive_rate": 0.01, "success_rate": 0.98}
    tests = {"t1": True, "t2": True}
    
    score = evaluator.evaluate(metrics, tests)
    assert score.level >= MaturityLevel.L3_HIGH_AUTONOMY
    assert score.dimension_scores["safety"] > 0.9

def test_low_safety_maturity():
    evaluator = MaturityEvaluator()
    
    # Low safety score
    metrics = {"safety_false_positive_rate": 0.3, "success_rate": 0.98}
    score = evaluator.evaluate(metrics, {})
    assert score.dimension_scores["safety"] < 0.8
    assert "Safety" in score.gaps[0]
