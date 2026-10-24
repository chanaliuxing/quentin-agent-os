import sys
from quentin.runtime.disaster_recovery import DisasterRecoveryOrchestrator

def main():
    dr = DisasterRecoveryOrchestrator()
    print("Starting DR snapshot...")
    snapshot_path = dr.create_snapshot()
    print(f"Snapshot created successfully: {snapshot_path}")

if __name__ == "__main__":
    main()
