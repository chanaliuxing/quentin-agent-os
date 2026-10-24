import pytest
from fastapi.testclient import TestClient
from meta_agent.api.server import app

client = TestClient(app)

def test_audit_export_flow():
    # 1. Export
    response = client.get("/audit/export")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "download_url" in data
    
    # 2. Fetch Evidence
    evidence_id = data["bundle_id"]
    response = client.get(f"/audit/evidence/{evidence_id}")
    assert response.status_code == 200
    assert response.json()["id"] == evidence_id
