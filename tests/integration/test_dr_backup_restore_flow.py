import pytest
import os
import shutil
from pathlib import Path
from quentin.runtime.disaster_recovery import DisasterRecoveryOrchestrator

def test_dr_backup_restore_lifecycle():
    repo_root = Path(".").resolve()
    dr = DisasterRecoveryOrchestrator(repo_root=str(repo_root))
    
    # 1. Prepare a test file
    test_file = repo_root / "config" / "dr_test_marker.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("v1_original")
    
    # 2. Create snapshot
    snapshot_path = dr.create_snapshot()
    snapshot_id = Path(snapshot_path).name
    
    # 3. Corrupt/Modify original file
    test_file.write_text("CORRUPTED")
    
    # 4. Restore
    success = dr.restore_from_snapshot(snapshot_id)
    assert success is True
    
    # 5. Verify restoration
    assert test_file.read_text() == "v1_original"
    
    # Cleanup
    if Path(snapshot_path).exists():
        shutil.rmtree(snapshot_path)
    test_file.unlink()
