import pytest
from quentin.governance.slo_registry import SLORegistry

def test_slo_defaults():
    registry = SLORegistry()
    slos = registry.list_all()
    assert "availability" in slos
    assert "latency_p95" in slos
    assert slos["availability"].target == 0.999
