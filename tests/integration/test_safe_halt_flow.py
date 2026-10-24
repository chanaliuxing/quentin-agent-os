import pytest
from quentin.safety.safe_halt_manager import SafeHaltManager

def test_safe_halt_trigger():
    manager = SafeHaltManager()
    
    # 1. Normal state
    assert manager.halt_active is False
    
    # 2. Trigger by telemetry
    triggered = manager.check_and_trigger({"safety_incident_count": 15})
    assert triggered is True
    assert manager.halt_active is True
    
    # 3. Resume
    manager.resume()
    assert manager.halt_active is False

def test_human_override_endpoint():
    from fastapi.testclient import TestClient
    from meta_agent.api.server import app
    import os
    
    client = TestClient(app)
    
    # 1. Trigger freeze_evolution
    response = client.post("/safety/override?action=freeze_evolution")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["evolution_frozen"] is True
    
    # 2. Verify FF_ROADMAP_EVOLUTION_V1 is "0"
    assert os.environ.get("FF_ROADMAP_EVOLUTION_V1") == "0"
