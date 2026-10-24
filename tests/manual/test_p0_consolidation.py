import sys
import asyncio
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def test_lane_orchestrator():
    print("Testing Lane Orchestrator...")
    from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
    
    results = []
    async def task(n):
        await asyncio.sleep(0.1)
        results.append(n)
        return n
        
    # Run in parallel lanes
    t1 = lane_orchestrator.run_in_lane("session_A", lambda: task(1))
    t2 = lane_orchestrator.run_in_lane("session_B", lambda: task(2))
    
    await asyncio.gather(t1, t2)
    
    if len(results) == 2:
        print("✅ Lanes OK")
    else:
        raise ValueError("Lane execution failed")

async def test_dirty_sync():
    print("Testing Dirty Sync...")
    from quentin.infra.sessions.dirty_sync import dirty_sync
    
    sid = "test_sess"
    dirty_sync.track_change(sid, {"a": 1})
    
    # Should not sync yet (small change)
    if dirty_sync.should_sync(sid):
        raise ValueError("Synced too early!")
        
    # Massive change
    dirty_sync.track_change(sid, {"data": "x" * 2000})
    if not dirty_sync.should_sync(sid):
        raise ValueError("Failed to trigger sync on threshold!")
        
    dirty_sync.mark_synced(sid)
    if dirty_sync.should_sync(sid):
        raise ValueError("Failed to reset state!")
        
    print("✅ Dirty Sync OK")

async def test_self_prog_safety():
    print("Testing Self-Prog Safety...")
    # Mock ToolManager
    class MockTM:
        async def call_tool(self, req, ctx):
            class Res: success = False; error = "PathGuard Blocked"
            if "bad.py" in req.payload["path"]:
                return Res()
            Res.success = True
            return Res()
            
    from quentin.self_programming.safety_wrapper import SelfProgrammingSafetyWrapper
    wrapper = SelfProgrammingSafetyWrapper(MockTM())
    
    try:
        await wrapper.safe_write_file("bad.py", "print('bad')")
        raise ValueError("Should have blocked bad.py")
    except PermissionError:
        print("✅ Safety Interceptor OK")

async def main():
    await test_lane_orchestrator()
    await test_dirty_sync()
    await test_self_prog_safety()

if __name__ == "__main__":
    asyncio.run(main())
