import pytest
from quentin.federation.node_registry import NodeRegistry, FederationNode

def test_node_lifecycle():
    registry = NodeRegistry()
    node = FederationNode(
        node_id="node-1", 
        environment="prod", 
        endpoint_url="http://node1", 
        trust_level="high",
        capabilities=["gpu_inference"]
    )
    
    # Register
    registry.register_node(node)
    assert registry.get_node("node-1") is not None
    
    # Heartbeat
    initial_hb = node.last_heartbeat
    registry.heartbeat("node-1")
    assert node.last_heartbeat >= initial_hb
    
    # Quarantine
    registry.quarantine_node("node-1")
    assert node.status == "quarantined"
