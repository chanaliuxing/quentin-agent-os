import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quentin.runtime.release_orchestrator import ReleaseOrchestrator

def test_flow():
    # Setup temp config
    repo_root = "."
    cfg_path = Path("config/openclaw_parity.yaml")
    
    # Backup
    backup = None
    if cfg_path.exists(): backup = cfg_path.read_text()
    
    try:
        orch = ReleaseOrchestrator(repo_root)
        
        # 1. Promote
        snap_id = orch.promote_to_staging({"test_flag_v1": True})
        
        # Verify
        with open(cfg_path) as f:
            data = yaml.safe_load(f)
            assert data["feature_flags"]["test_flag_v1"] is True
            
        # 2. Rollback
        # First ensure we have a snapshot to rollback TO (the one created BEFORE update)
        # Wait, create_snapshot saves CURRENT state. So snap_id contains state BEFORE update.
        # Let's verify snapshot content
        snap = orch.snapshot_mgr.load_snapshot(snap_id)
        # Original state probably didn't have test_flag_v1 or it was whatever default
        
        orch.rollback(snap_id)
        
        # Verify rollback
        with open(cfg_path) as f:
            data = yaml.safe_load(f)
            # Should not have test_flag_v1 if it wasn't there before
            assert "test_flag_v1" not in data.get("feature_flags", {})
            
        print("ReleaseOrchestrator: OK")
        
    finally:
        if backup: cfg_path.write_text(backup)

if __name__ == "__main__":
    test_flow()
