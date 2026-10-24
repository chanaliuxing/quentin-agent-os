import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.infra.utils.pruning import prune_text
from quentin.runtime.system_events import SystemEventQueue

def test_pruning():
    print("Testing Pruning...")
    long_text = "A" * 2000
    pruned = prune_text(long_text, max_chars=100)
    if "... [PRUNED" in pruned:
        print("Pruning: OK")
    else:
        raise ValueError("Pruning failed")

def test_event_queue():
    print("Testing EventQueue...")
    queue = SystemEventQueue()
    queue.enqueue_event(
        event_type="test_alert",
        payload={"msg": "hello"},
        source="test_source",
        session_id="session_123"
    )
    events = queue.get_pending_events(session_id="session_123")
    if len(events) == 1 and events[0]["session_id"] == "session_123":
        print("EventQueue: OK")
    else:
        raise ValueError("EventQueue failed")

if __name__ == "__main__":
    test_pruning()
    test_event_queue()
    print("ALL MODULES OK")
