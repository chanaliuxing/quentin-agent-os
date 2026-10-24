import json
import sys
import os
from unittest.mock import MagicMock

# Ensure we're importing from the local quentin package
sys.path.insert(0, os.getcwd())

from quentin.cognitive.loop_orchestration import run_semantic_presensing_short_circuit
from quentin.execution.skill_executor import Executor

# --- Test Physical Guard Fix ---
def test_physical_guard_fix():
    print("Testing Physical Guard Fix (run_semantic_presensing_short_circuit)...")
    
    mock_loop = MagicMock()
    mock_loop.council_manager.run_council.return_value = MagicMock(
        final={"verdict": "already_done", "confidence": "1.0", "evidence_summary": "I see it!"}
    )
    mock_task = MagicMock(task_id="t1", input_text="Check if file exists")
    mock_goal = MagicMock(goal_id="g1")
    
    focus_paths = ["missing_file.yaml"]
    sensing_report = {
        "focus_paths": focus_paths,
        "evidence": [
            {
                "path": "missing_file.yaml",
                "exists": False,
                "is_dir": False
            }
        ]
    }
    
    def mock_result_factory(**kwargs):
        return MagicMock(**kwargs)
    
    # We need to mock a lot of stuff because it's complex
    mock_loop._infer_pre_sensing_focus_paths.return_value = focus_paths
    mock_loop._generate_sensing_report.return_value = sensing_report
    mock_loop._planner = None # Ensure it doesn't return None early
    
    # We call it directly
    res = run_semantic_presensing_short_circuit(
        loop=mock_loop,
        task=mock_task,
        goal=mock_goal,
        trace_id="tr1",
        result_factory=mock_result_factory
    )
    
    if res is None:
        print("✅ Success: run_semantic_presensing_short_circuit returned None (blocked hallucination)")
    else:
        print(f"❌ Failure: run_semantic_presensing_short_circuit returned {res} (failed to block hallucination)")

# --- Test Step Termination Fix ---
def test_step_termination_fix():
    print("\nTesting Step Termination Fix (_should_end_step_after_tool_call)...")
    
    tool_call = {"tool_name": "fs.write_file", "args": {"path": "test.txt", "content": "hello"}}
    tool_res = MagicMock(success=True)
    desc = "Writing the file test.txt"
    
    res = Executor._should_end_step_after_tool_call(desc=desc, tool_call=tool_call, tool_res=tool_res)
    
    if res is True:
        print("✅ Success: _should_end_step_after_tool_call returned True for write_file")
    else:
        print("❌ Failure: _should_end_step_after_tool_call returned False for write_file")

    # Test search_replace
    tool_call_sr = {"tool_name": "fs.search_replace", "args": {"path": "test.txt", "old_str": "a", "new_string": "b"}}
    res_sr = Executor._should_end_step_after_tool_call(desc="Replacing text", tool_call=tool_call_sr, tool_res=tool_res)
    if res_sr is True:
        print("✅ Success: _should_end_step_after_tool_call returned True for search_replace")
    else:
        print("❌ Failure: _should_end_step_after_tool_call returned False for search_replace")

if __name__ == "__main__":
    test_physical_guard_fix()
    test_step_termination_fix()
