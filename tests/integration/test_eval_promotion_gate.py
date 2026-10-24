import pytest
from quentin.eval.experiment_hub import ExperimentHub
from quentin.eval.promotion_policy import PromotionPolicy

def test_promotion_gate_logic():
    hub = ExperimentHub()
    policy = PromotionPolicy(hub)
    
    # 1. Fail case (below threshold)
    hub.record_result("low_quality_exp", {"success_rate": 0.80, "quality_score": 0.70})
    assert policy.can_promote("low_quality_exp") is False
    
    # 2. Pass case
    hub.record_result("high_quality_exp", {"success_rate": 0.98, "quality_score": 0.85})
    assert policy.can_promote("high_quality_exp") is True
