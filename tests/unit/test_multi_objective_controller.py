import pytest
from quentin.optimization.multi_objective_controller import MultiObjectiveController, OptimizationWeights

def test_multi_objective_scoring():
    ctrl = MultiObjectiveController()
    
    # Candidate 1: High quality, low cost
    m1 = {"quality": 0.9, "safety": 0.9, "cost_normalized": 0.1, "latency_normalized": 0.1}
    # Candidate 2: Low quality, high cost
    m2 = {"quality": 0.5, "safety": 0.5, "cost_normalized": 0.9, "latency_normalized": 0.9}
    
    s1 = ctrl.evaluate_proposal(m1)
    s2 = ctrl.evaluate_proposal(m2)
    
    assert s1 > s2
