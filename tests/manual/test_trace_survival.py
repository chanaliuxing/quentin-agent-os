import sys
from pathlib import Path
import os
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def test_survival():
    from quentin.traces.core import JsonlTraceRecorder
    print("Testing TraceRecorder Survival...")
    
    recorder = JsonlTraceRecorder(repo_root=".")
    trace_dir = Path("./data/traces")
    
    # 1. Normal Write
    recorder.record_event(trace_id="t1", event_type="test", payload={"msg": "first"})
    if not (trace_dir / "events.jsonl").exists():
        raise ValueError("First write failed")
    print("First write: OK")

    # 2. Chaos: Delete the whole directory
    print("Simulating directory deletion...")
    shutil.rmtree(trace_dir)
    
    # 3. Survival Write
    recorder.record_event(trace_id="t2", event_type="test", payload={"msg": "survive"})
    
    if (trace_dir / "events.jsonl").exists():
        print("Survival write: OK (Self-Healed)")
    else:
        raise ValueError("TraceRecorder failed to recover from deletion")

if __name__ == "__main__":
    try:
        test_survival()
        print("SUCCESS")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
