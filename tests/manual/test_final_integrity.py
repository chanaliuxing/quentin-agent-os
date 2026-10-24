import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def run_final_check():
    from quentin.tools.manager import ToolManager
    from quentin.execution.skill_executor import Executor
    from quentin.runtime.system_events import system_events
    
    # 1. Check SystemEvents
    system_events.enqueue_event(event_type="test", payload={}, session_id="s1")
    evs = system_events.consume_pending(session_id="s1")
    print("SystemEvents: OK")

    # 2. Check Executor with REAL loop_impl signature
    tm = ToolManager()
    tm.register("ls", lambda p, c=None: {"files": []})
    exe = Executor(repo_root=".", tool_manager=tm)
    
    plan_mock = type('Plan', (), {'steps': [{"step_id": "s1", "description": "test"}]})()
    
    print("Testing Executor...")
    # This matches loop_impl.py:1822
    await exe.execute_plan(
        goal=None,
        plan=plan_mock,
        context={}
    )
    print("Executor: OK")

if __name__ == "__main__":
    try:
        asyncio.run(run_final_check())
        print("🚀 ALL SYSTEMS CLEAR")
    except Exception as e:
        print("❌ FAILED: " + str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)
