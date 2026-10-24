import pytest
from quentin.ecosystem.cert_kit import CertificationKit
from quentin.ecosystem.cert_registry import CertificationRegistry

def test_full_certification_flow():
    kit = CertificationKit()
    registry = CertificationRegistry()
    
    # 1. Target node info
    target = {"id": "external-node-1", "version": "1.0.0", "safety_enabled": True}
    
    # 2. Run certification
    res = kit.run_tests(target)
    assert res["passed"] is True
    
    # 3. Register Certificate
    cert_id = registry.register_cert(target["id"])
    assert registry.verify_cert(cert_id) is True
