
import os
import json
import asyncio
from unittest.mock import MagicMock, patch
from quentin.cognitive.loop_orchestration import run_semantic_presensing_short_circuit

class MockTask:
    def __init__(self, input_text):
        self.input_text = input_text
        self.task_id = "test_task"
        self.domain = "core"
        self.environment = "sandbox"
        self.metadata = {}

class MockGoal:
    def __init__(self, goal_id):
        self.goal_id = goal_id
        self.title = "Test Goal"

def test_hallucination():
    print("Testing Pre-sensing Hallucination...")
    
    # Task: Create a directory that doesn't exist
    task = MockTask("Create directory extensions/tools/web_search/")
    goal = MockGoal("test_goal")
    
    loop = MagicMock()
    loop._planner = None # CRITICAL
    loop._infer_pre_sensing_focus_paths.return_value = ["extensions/tools/web_search/"]
    # Sensing report shows NOTHING in the focused path
    loop._generate_sensing_report.return_value = {
        "extensions/tools/web_search/": {
            "exists": False,
            "error": "Directory not found"
        }
    }
    
    def mock_run_council(topic, question):
        print(f"\n--- Pre-sensing Prompt Sent to LLM ---\n{question.prompt}\n--- End Prompt ---")
        res = MagicMock()
        res.final = {
            "verdict": "already_done",
            "evidence_summary": "The directory extensions/tools/web_search/ is mentioned in the task and is thus done.",
            "confidence": 0.98
        }
        return res

    loop.council_manager.run_council = mock_run_council
    
    result_factory = MagicMock()
    
    os.environ["QUENTIN_ENABLE_PRE_SENSING"] = "1"
    
    # Run the function
    res = run_semantic_presensing_short_circuit(
        loop,
        task=task,
        goal=goal,
        trace_id="test_trace",
        result_factory=result_factory
    )
    
    if res:
        print("\n✅ Success: Pre-sensing logic executed and returned result (as mocked).")
    else:
        print("\n❌ Failure: Pre-sensing logic did NOT execute.")

if __name__ == "__main__":
    test_hallucination()
