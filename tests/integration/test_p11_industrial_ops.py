import pytest
from quentin.ops.control_tower import OperationsControlTower, TowerSnapshot
from quentin.governance.error_budget import ErrorBudgetController
from quentin.governance.slo_registry import SLORegistry

def test_control_tower_aggregation_logic():
    slo_reg = SLORegistry()
    error_budget = ErrorBudgetController(slo_reg)
    
    # Exhaust one budget to test risk identification
    error_budget.report_error("availability", 1.0)
    
    tower = OperationsControlTower(error_budget=error_budget)
    snapshot = tower.get_overview()
    
    assert snapshot.health_status == "degraded"
    assert any(r["id"] == "slo_exhausted_availability" for r in snapshot.active_risks)

def test_domain_template_and_factory():
    from quentin.blueprint.domain_template_spec import DomainTemplateSpec
    from quentin.blueprint.domain_factory import DomainFactory
    from quentin.blueprint.domain_validator import DomainValidator
    import shutil
    import os
    
    spec = DomainTemplateSpec(domain_name="test_factory")
    validator = DomainValidator()
    
    # 1. Validate
    errors = validator.validate(spec)
    assert not errors
    
    # 2. Generate
    factory = DomainFactory(repo_root=".")
    path = factory.generate_domain(spec)
    
    assert os.path.exists(path)
    assert os.path.exists(os.path.join(path, "config.yaml"))
    
    # Cleanup
    if os.path.exists(path):
        shutil.rmtree(path)

def test_change_pipeline_workflow():
    from quentin.governance.change_request import ChangeRequest
    from quentin.governance.change_pipeline import ChangePipelineOrchestrator
    
    orch = ChangePipelineOrchestrator()
    req = ChangeRequest(title="Upgrade Kernel", scope="global", risk_level="high")
    
    # 1. Submit
    req_id = orch.submit_change(req)
    assert req_id in orch.requests
    
    # 2. Analyze
    analysis = orch.analyze_impact(req_id)
    assert analysis["risk_score"] > 0
    assert orch.requests[req_id].status == "analyzing"
    
    # 3. Rollback
    orch.rollback_change(req_id)
    assert orch.requests[req_id].status == "rolled_back"

def test_roi_estimation_pipeline():
    from quentin.analytics.outcome_metrics import OutcomeMetrics
    from quentin.analytics.roi_estimator import ROIEstimator
    
    estimator = ROIEstimator()
    metrics = OutcomeMetrics(domain="test", activity_count=100, success_rate=1.0, time_saved_hours=10, cost_reduction_usd=100, risk_suppression_count=1)
    
    roi = estimator.estimate_roi(metrics)
    assert roi["value_generated_usd"] == 600.0 # (10 * 50) + 100
    assert roi["system_cost_usd"] == 5.0 # 100 * 0.05
    assert roi["net_gain_usd"] == 595.0
