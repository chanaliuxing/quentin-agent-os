import pytest
from quentin.interoperability.safety_gate import InteropSafetyGate

def test_interop_safety_redaction():
    gate = InteropSafetyGate()
    
    external_input = {
        "user": "alice",
        "api_key": "sk-secret-123",
        "data": "important payload"
    }
    
    sanitized = gate.sanitize_external_input(external_input)
    assert sanitized["api_key"] == "[REDACTED_BY_INTEROP_GATE]"
    assert sanitized["user"] == "alice"
