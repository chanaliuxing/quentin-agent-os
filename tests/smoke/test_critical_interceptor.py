import asyncio
import logging
import json
from unittest.mock import MagicMock
from quentin.cognitive.loop_orchestration import handle_attempt_execution_and_feedback, LoopRuntimeState

# Silence normal logging
logging.getLogger("quentin").setLevel(logging.CRITICAL)

async def test_critical_failure_interceptor():
    print("\n[SMOKE TEST] Verifying Critical Failure Interceptor...")
    
    # 1. Setup mock loop and state
    loop = MagicMock()
    loop._sanitize_executor_output.return_value = ("output", "summary")
    loop._update_circuit_breaker_state.return_value = (0, "", None, False)
    loop._detect_execution_antipattern.return_value = {"detected": False}
    loop._is_tool_only_no_update.return_value = False
    
    state = LoopRuntimeState()
    
    # 2. Mock execution result with critical failure
    exec_res = {
        "raw": {
            "success": False,
            "steps": [
                {
                    "step_id": "s1",
                    "result": {
                        "status": "error",
                        "error": "mkdir on file path",
                        "critical_failure": True,
                        "error_code": "TOOL_MISUSE_MKDIR_ON_FILE"
                    }
                }
            ]
        }
    }
    
    # 3. Call handler
    feedback = await handle_attempt_execution_and_feedback(
        loop=loop,
        task=MagicMock(),
        goal=MagicMock(),
        trace_id="test-trace",
        session_id="test-session",
        loop_idx=1,
        plan_result=MagicMock(),
        plan_summary="test plan",
        exec_res=exec_res,
        attempt_started_at=None,
        metrics={"total_attempts": 1, "success_attempts": 0, "error_attempts": 0},
        state=state,
        recent_traces=[],
        recent_snapshots=[],
        latest_self_awareness=MagicMock(),
        self_awareness_engine=MagicMock(),
        failure_count=0,
        tool_only_no_update_count=0,
        consecutive_errors=0,
        last_error_msg="",
        current_think_level="off",
        attempted_thinking=set(),
        overflow_compacted=False
    )
    
    # 4. Assert break and reflection trigger
    print(f"Should break: {feedback.get('should_break')}")
    print(f"Failure count: {feedback.get('failure_count')}")
    print(f"Error msg: {feedback.get('last_error_msg')}")
    
    assert feedback.get("should_break") is True
    assert feedback.get("failure_count") >= 3 # Forced reflection threshold
    assert "critical_failure" in feedback.get("last_error_msg")
    
    print("✅ Critical failure interceptor verified.")

if __name__ == "__main__":
    try:
        asyncio.run(test_critical_failure_interceptor())
        print("\n✨ INTERCEPTOR TEST PASSED")
    except Exception as e:
        print(f"\n❌ INTERCEPTOR TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
