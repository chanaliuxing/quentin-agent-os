import sys
from quentin.runtime.disaster_recovery import DisasterRecoveryOrchestrator

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/dr_restore.py <snapshot_id>")
        sys.exit(1)
    
    snapshot_id = sys.argv[1]
    dr = DisasterRecoveryOrchestrator()
    print(f"Restoring from snapshot {snapshot_id}...")
    success = dr.restore_from_snapshot(snapshot_id)
    if success:
        print("Restoration complete.")
    else:
        print("Restoration failed: Snapshot not found.")

if __name__ == "__main__":
    main()
