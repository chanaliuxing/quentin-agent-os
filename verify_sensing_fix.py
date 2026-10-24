
import json
import unittest
from unittest.mock import MagicMock
from quentin.cognitive.loop_orchestration import run_semantic_presensing_short_circuit

class MockGoal:
    def __init__(self, goal_id: str):
        self.goal_id = goal_id

class MockTask:
    def __init__(self, input_text: str, task_id: str):
        self.input_text = input_text
        self.task_id = task_id

class TestSensingHallucination(unittest.TestCase):
    def test_hallucination_blocked(self):
        loop = MagicMock()
        loop._planner = None
        loop._infer_pre_sensing_focus_paths.return_value = ["ghost.txt"]
        
        # Mock sensing report structure as returned by _generate_sensing_report
        loop._generate_sensing_report.return_value = {
            "evidence": [
                {"path": "ghost.txt", "exists": False}
            ]
        }
        
        # Mock council response claiming it's done
        mock_res = MagicMock()
        mock_res.final = {"verdict": "already_done", "confidence": 0.99, "evidence_summary": "I see it!"}
        loop.council_manager.run_council.return_value = mock_res
        
        task = MockTask("create ghost.txt", "t1")
        goal = MockGoal("g1")
        
        # We need to mock result_factory too
        def mock_factory(**kwargs):
            return kwargs
        
        res = run_semantic_presensing_short_circuit(
            loop,
            task=task,
            goal=goal,
            trace_id="tr1",
            result_factory=mock_factory
        )
        
        # If blocked, it should return None
        self.assertIsNone(res)
        print("✅ Hallucination successfully blocked by physical guard!")

    def test_genuine_done_not_blocked(self):
        loop = MagicMock()
        loop._planner = None
        loop._infer_pre_sensing_focus_paths.return_value = ["real.txt"]
        
        loop._generate_sensing_report.return_value = {
            "evidence": [
                {"path": "real.txt", "exists": True}
            ]
        }
        
        mock_res = MagicMock()
        mock_res.final = {"verdict": "already_done", "confidence": 0.99, "evidence_summary": "It exists."}
        loop.council_manager.run_council.return_value = mock_res
        
        task = MockTask("check real.txt", "t1")
        goal = MockGoal("g1")
        
        def mock_factory(**kwargs):
            return kwargs
        
        res = run_semantic_presensing_short_circuit(
            loop,
            task=task,
            goal=goal,
            trace_id="tr1",
            result_factory=mock_factory
        )
        
        # If not blocked, it should return the result (dict in our mock)
        self.assertIsNotNone(res)
        self.assertEqual(res["done"], True)
        print("✅ Genuine completion NOT blocked.")

if __name__ == "__main__":
    unittest.main()
