import json
import logging
from unittest.mock import MagicMock
from quentin.cognitive.loop_orchestration import run_semantic_presensing_short_circuit

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_sensing_hallucination_fix():
    print("Testing Sensing Hallucination Fix...")
    
    # Mock Loop object
    loop = MagicMock()
    loop._planner = None
    
    # Mock task and goal
    task = MagicMock()
    task.input_text = "Create a new file named 'missing_file.txt'"
    goal = MagicMock()
    goal.goal_id = "test_goal"
    
    # Mock result_factory
    def result_factory(**kwargs):
        return kwargs
    
    # 1. Simulate the Hallucination Scenario
    # Focus paths include the missing file
    loop._infer_pre_sensing_focus_paths.return_value = ["missing_file.txt"]
    # Sensing report says it does NOT exist
    sensing_report = {
        "missing_file.txt": {"exists": False}
    }
    loop._generate_sensing_report.return_value = sensing_report
    
    # Council says "already_done" (The Hallucination)
    council_res = MagicMock()
    council_res.final = {
        "verdict": "already_done",
        "confidence": 0.98,
        "evidence_summary": "I hallucinated that the file exists because I'm a confident LLM."
    }
    loop.council_manager.run_council.return_value = council_res
    
    # Run pre-sensing
    result = run_semantic_presensing_short_circuit(
        loop,
        task=task,
        goal=goal,
        trace_id="test_trace",
        result_factory=result_factory
    )
    
    if result is not None and result.get("done") is True:
        print("❌ FAIL: Pre-sensing returned 'already_done' despite 'exists: False' in sensing report.")
    else:
        print("✅ PASS: Pre-sensing blocked the hallucination (or returned None).")

if __name__ == "__main__":
    test_sensing_hallucination_fix()
