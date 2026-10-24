import uuid
import time
import json
import hashlib
from quentin.audit.export_schema import AuditBundle

def main():
    # Mock events for export
    events = [
        {"id": "e1", "actor": "selfprog", "action": "patch", "decision": "allow"},
        {"id": "e2", "actor": "operator", "action": "run_task", "decision": "block"}
    ]
    
    events_json = json.dumps(events, sort_keys=True)
    integrity_hash = hashlib.sha256(events_json.encode()).hexdigest()
    
    bundle = AuditBundle(
        bundle_id=f"bundle-{uuid.uuid4().hex[:8]}",
        exported_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        events=events,
        integrity_hash=integrity_hash
    )
    
    print(bundle.to_json())

if __name__ == "__main__":
    main()
