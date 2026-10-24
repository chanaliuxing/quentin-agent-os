import pytest
from quentin.eval.experiment_hub import ExperimentHub

def test_experiment_result_aggregation():
    hub = ExperimentHub()
    exp_id = "routing_v2_tuning"
    
    # Record multiple runs
    hub.record_result(exp_id, {"success_rate": 0.90, "latency": 1500})
    hub.record_result(exp_id, {"success_rate": 0.96, "latency": 1300})
    
    # Verify summary (averaging)
    summary = hub.get_summary(exp_id)
    assert summary["success_rate"] == pytest.approx(0.93)
    assert summary["latency"] == 1400
