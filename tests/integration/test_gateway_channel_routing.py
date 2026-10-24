import sys
import asyncio
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.infra.channels.gateway_server import gateway
from quentin.config.feature_flags import feature_flags

def test_gateway_routing():
    # Mock flags
    import os
    os.environ["FF_GATEWAY_V1"] = "1"
    
    client = TestClient(gateway.app)
    
    # 1. Inbound
    resp = client.post("/gateway/messages/inbound", json={
        "channel": "test",
        "sender_id": "u1",
        "chat_id": "c1",
        "text": "Hello Gateway"
    })
    
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert "lane" in resp.json()
    
    print("GatewayRouting: OK")

if __name__ == "__main__":
    test_gateway_routing()
