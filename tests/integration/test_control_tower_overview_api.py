import pytest
from fastapi.testclient import TestClient
from meta_agent.api.server import app

client = TestClient(app)

def test_api_tower_overview():
    response = client.get("/ops/control-tower/overview")
    assert response.status_code == 200
    data = response.json()
    assert "health_status" in data
    assert "active_risks" in data

def test_api_tower_incidents():
    response = client.get("/ops/control-tower/incidents")
    assert response.status_code == 200
    data = response.json()
    assert "incidents" in data
    assert data["count"] >= 1

def test_api_change_request_flow():
    # 1. Submit
    response = client.post("/governance/changes?title=TestChange&scope=web&risk=low")
    assert response.status_code == 200
    change_id = response.json()["change_id"]
    
    # 2. Get status
    response = client.get(f"/governance/changes/{change_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "TestChange"
