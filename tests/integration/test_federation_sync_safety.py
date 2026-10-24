import pytest
from quentin.federation.sync_filter import SyncFilter
from quentin.federation.sync_orchestrator import SyncOrchestrator

def test_sync_filter_safety():
    f = SyncFilter()
    data = {
        "model_name": "gpt-4",
        "api_key": "sk-12345",
        "user_pii": "john@doe.com"
    }
    
    filtered = f.filter_payload(data)
    assert "model_name" in filtered
    assert "api_key" not in filtered
    assert "user_pii" not in filtered

def test_sync_orchestrator_packet():
    orch = SyncOrchestrator()
    data = {"safe": "value", "secret": "hidden"}
    
    packet = orch.prepare_sync_packet(data, "node-2")
    assert packet.target_node == "node-2"
    assert "safe" in packet.payload
    assert "secret" not in packet.payload
