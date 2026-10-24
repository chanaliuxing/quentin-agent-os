import pytest
from quentin.governance.error_budget import ErrorBudgetController
from quentin.governance.slo_registry import SLORegistry

def test_error_budget_exhaustion():
    registry = SLORegistry()
    controller = ErrorBudgetController(registry)
    
    # Report enough errors to exhaust the budget
    for _ in range(200):
        controller.report_error("availability", 0.01)
        
    assert controller.is_degradation_required()
    mode = controller.get_degradation_mode()
    assert mode["mode"] == "degrade"
    assert mode["disable_high_risk_evolution"] is True
