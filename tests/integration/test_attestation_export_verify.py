import pytest
import json
import hashlib
from quentin.trust.attestation_builder import AttestationBuilder

def test_attestation_verification_roundtrip():
    builder = AttestationBuilder()
    telemetry = {"policy_compliance_rate": 0.95, "safety_incidents": 1}
    attest = builder.build(telemetry)
    
    # 1. Simulating external verification
    data = attest.__dict__.copy()
    received_sig = data.pop("signature")
    
    payload = json.dumps(data, sort_keys=True)
    recalculated_sig = hashlib.sha256(payload.encode()).hexdigest()
    
    assert recalculated_sig == received_sig
