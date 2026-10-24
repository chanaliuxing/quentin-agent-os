import pytest
from fastapi.testclient import TestClient
from meta_agent.api.server import app

client = TestClient(app)

def test_api_list_capabilities():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert data["total"] >= 2 # From bootstrap

def test_api_capability_lifecycle():
    # 1. List to get an ID
    response = client.get("/capabilities")
    cap_id = response.json()["capabilities"][0]["id"]
    
    # 2. Promote
    response = client.post(f"/capabilities/{cap_id}/promote")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    
    # 3. Verify status
    response = client.get("/capabilities")
    caps = response.json()["capabilities"]
    target = next(c for c in caps if c["id"] == cap_id)
    assert target["status"] == "trusted"
