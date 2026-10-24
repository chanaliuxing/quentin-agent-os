import pytest
from fastapi.testclient import TestClient
from meta_agent.api.server import app

client = TestClient(app)

def test_api_health_p3():
    response = client.get("/health/p3")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "p3_metrics" in data
    assert "feature_flags" in data
    assert "chaos_drill" in data["feature_flags"]
