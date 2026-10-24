import pytest
from quentin.safety.kill_switch_mesh import KillSwitchMesh
from quentin.safety.recovery_grid import RecoveryGrid

def test_kill_switch_suppression():
    mesh = KillSwitchMesh()
    
    # 1. No suppression initially
    assert mesh.is_suppressed("node-1", "core") is False
    
    # 2. Trigger domain switch
    mesh.trigger("domain:core")
    assert mesh.is_suppressed("node-1", "core") is True
    assert mesh.is_suppressed("node-1", "web") is False
    
    # 3. Trigger global switch
    mesh.trigger("global")
    assert mesh.is_suppressed("node-1", "web") is True

def test_recovery_status_flow():
    grid = RecoveryGrid()
    
    grid.start_recovery("domain:core")
    assert grid.get_status("domain:core") == "baseline_validation"
