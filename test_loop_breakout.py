import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from quentin.cognitive.loop_orchestration import handle_attempt_execution_and_feedback, LoopRuntimeState

class MockTask:
    def __init__(self):
        self.task_id = "test_task"
        self.domain = "core"
        self.environment = "sandbox"
        self.metadata = {}

class MockGoal:
    def __init__(self):
        self.goal_id = "test_goal"

async def test_loop_detection():
    print("Testing Repetitive Tool Loop Detection...")
    
    state = LoopRuntimeState()
    loop = MagicMock()
    # Mock loop methods used in handle_attempt_execution_and_feedback
    loop._sanitize_executor_output.return_value = ("output", "summary")
    loop._update_circuit_breaker_state.return_value = (0, "", "", False)
    loop._detect_execution_antipattern.return_value = {"detected": False}
    loop._is_tool_only_no_update.return_value = False
    loop._extract_attempt_metrics.return_value = {"cost_tokens": 0, "latency_ms": 0, "tool_calls": 1, "prediction_errors": 0}
    loop._flush_memory = AsyncMock()
    loop._evaluate_attempt_outcome.return_value = (MagicMock(is_done=False, confidence=0.0), 0, False)
    
    task = MockTask()
    goal = MockGoal()
    self_awareness_engine = MagicMock()
    self_awareness_engine.observe_attempt.return_value = MagicMock(
        status="ok", failure_rate=0.0, failover_reason="", consecutive_system_errors=0,
        anti_pattern_reason="", suggested_actions=[]
    )
    
    # Simulate 3 attempts with identical tool calls
    tool_call = {
        "tool_name": "fs_mkdir",
        "arguments": {"path": "extensions/tools/web_search/"}
    }
    
    exec_res = {
        "raw": {
            "success": True,
            "steps": [
                {
                    "result": {
                        "call_tool": tool_call
                    }
                }
            ]
        }
    }
    
    metrics = {"total_attempts": 0, "success_attempts": 0, "error_attempts": 0, "cost_tokens": 0, "latency_ms": 0, "tool_call_count": 0, "prediction_error_count": 0, "prediction_error_rate": 0.0}
    
    # First attempt
    print("\nAttempt 1...")
    metrics["total_attempts"] += 1
    feedback1 = await handle_attempt_execution_and_feedback(
        loop, task=task, goal=goal, trace_id="t1", session_id="s1", loop_idx=1,
        plan_result=MagicMock(steps=[]), plan_summary="", exec_res=exec_res,
        attempt_started_at=None, metrics=metrics,
        state=state, recent_traces=[], recent_snapshots=[], latest_self_awareness=MagicMock(status="ok"),
        self_awareness_engine=self_awareness_engine, failure_count=0, tool_only_no_update_count=0,
        consecutive_errors=0, last_error_msg="", current_think_level="off", attempted_thinking=set(),
        overflow_compacted=False
    )
    print(f"Feedback 1 actions_summary: {feedback1.get('actions_summary')}")
    
    # Second attempt (identical)
    print("\nAttempt 2...")
    metrics["total_attempts"] += 1
    feedback2 = await handle_attempt_execution_and_feedback(
        loop, task=task, goal=goal, trace_id="t1", session_id="s1", loop_idx=2,
        plan_result=MagicMock(steps=[]), plan_summary="", exec_res=exec_res,
        attempt_started_at=None, metrics=metrics,
        state=state, recent_traces=[], recent_snapshots=[], latest_self_awareness=MagicMock(status="ok"),
        self_awareness_engine=self_awareness_engine, failure_count=0, tool_only_no_update_count=0,
        consecutive_errors=0, last_error_msg="", current_think_level="off", attempted_thinking=set(),
        overflow_compacted=False
    )
    
    # Third attempt (identical) -> Should trigger loop breakout
    print("\nAttempt 3 (Identical)...")
    metrics["total_attempts"] += 1
    feedback3 = await handle_attempt_execution_and_feedback(
        loop, task=task, goal=goal, trace_id="t1", session_id="s1", loop_idx=3,
        plan_result=MagicMock(steps=[]), plan_summary="", exec_res=exec_res,
        attempt_started_at=None, metrics=metrics,
        state=state, recent_traces=[], recent_snapshots=[], latest_self_awareness=MagicMock(status="ok"),
        self_awareness_engine=self_awareness_engine, failure_count=0, tool_only_no_update_count=0,
        consecutive_errors=0, last_error_msg="", current_think_level="off", attempted_thinking=set(),
        overflow_compacted=False
    )
    
    print(f"Feedback 3 should_break: {feedback3.get('should_break')}")
    print(f"Feedback 3 actions_summary: {feedback3.get('actions_summary')}")
    print(f"Critical Instruction: '{state.critical_instruction}'")
    
    if state.critical_instruction and not feedback3.get('should_break'):
        print("\n✅ Success: Loop detected and breakout instruction injected without breaking the loop!")
    else:
        print("\n❌ Failure: Loop detection or breakout injection failed.")

if __name__ == "__main__":
    asyncio.run(test_loop_detection())
