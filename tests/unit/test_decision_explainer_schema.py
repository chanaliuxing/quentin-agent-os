import pytest
from quentin.explainability.decision_explainer import DecisionExplainer

def test_explanation_generation():
    explainer = DecisionExplainer()
    context = {"id": "dec-123"}
    decision = {"action": "scale_up", "score": 0.95}
    
    explanation = explainer.explain(context, decision)
    assert explanation.outcome == "scale_up"
    assert explanation.factors["score"] == 0.95
    assert "scale_up" in explanation.narrative
