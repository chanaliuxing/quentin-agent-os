import pytest
from quentin.safety.kill_switch_mesh import KillSwitchMesh

def test_kill_switch_hierarchical_resolution():
    mesh = KillSwitchMesh()
    
    # 1. Domain level
    mesh.trigger("domain:web")
    assert mesh.is_suppressed("node-any", "web") is True
    assert mesh.is_suppressed("node-any", "core") is False
    
    # 2. Node level
    mesh.trigger("node:node-1")
    assert mesh.is_suppressed("node-1", "core") is True
    assert mesh.is_suppressed("node-2", "core") is False
    
    # 3. Global level override
    mesh.trigger("global")
    assert mesh.is_suppressed("node-2", "core") is True
