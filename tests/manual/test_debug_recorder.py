import sys
from pathlib import Path
import os

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType

def test_recorder():
    print("Testing TraceRecorder...")
    recorder = JsonlTraceRecorder(repo_root=".")
    print(f"Events path: {recorder._events_path}")
    
    event = new_trace_event(trace_id="test_id", event_type=TraceEventType.TASK_RECEIVED, payload={"test": "data"})
    recorder.record_event(event)
    
    if recorder._events_path.exists():
        print(f"✅ Success: {recorder._events_path} exists.")
        print(f"Content: {recorder._events_path.read_text()}")
    else:
        print(f"❌ Failure: {recorder._events_path} does NOT exist.")

if __name__ == "__main__":
    test_recorder()
