import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def run_test():
    print("Testing SystemEvents...")
    from quentin.runtime.system_events import system_events, SystemEventQueue
    system_events.enqueue_event(event_type="test", payload={}, session_id="c1")
    # Verify the specific missing method
    evs = system_events.consume_pending(session_id="c1")
    if len(evs) >= 1:
        print("SystemEvents: OK")
    else:
        raise ValueError("consume_pending failed to return events")

    print("Testing ToolManager...")
    from quentin.tools.manager import ToolManager, ToolCallContext
    from quentin.tools.schemas import ToolCallRequest
    tm = ToolManager()
    def h(p, c=None): return {"val": p.get("k")}
    tm.register("t1", h)
    req = ToolCallRequest(tool_name="t1", payload={"k": "v"})
    res = asyncio.run(tm.call_tool(req, ToolCallContext()))
    if res.output.get("val") == "v":
        print("ToolManager: OK")
    else:
        raise ValueError("ToolManager output mismatch")

    print("Testing Imports...")
    from quentin.cognitive.loop_impl import CognitiveLoop
    print("Imports: OK")

if __name__ == "__main__":
    try:
        run_test()
        print("SUCCESS")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)
