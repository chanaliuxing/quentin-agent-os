import pytest
import json
from quentin.trust.attestation_builder import AttestationBuilder

def test_attestation_builder_integrity():
    builder = AttestationBuilder()
    telemetry = {"policy_compliance_rate": 0.99, "safety_incidents": 0}
    
    attest = builder.build(telemetry)
    
    # Verify required fields
    assert attest.attestation_id.startswith("attest-")
    assert attest.governance_score == 0.99
    assert len(attest.signature) == 64 # SHA256 length
    
    # Verify that changing telemetry results in different signature
    attest2 = builder.build({"policy_compliance_rate": 0.50, "safety_incidents": 10})
    assert attest.signature != attest2.signature
