from __future__ import annotations

from quentin.cognitive.attempt_evaluator import evaluate_attempt_result


def test_repeated_tool_call_loop_classifies_as_logic_path_error() -> None:
    exec_res = {
        "final_output": "",
        "actions_summary": "executor reported repeated_tool_call_loop",
        "raw": {
            "success": False,
            "steps": [
                {
                    "step_id": "s1",
                    "success": False,
                    "result": {
                        "status": "error",
                        "error": "repeated_tool_call_loop",
                        "call_tool": {"tool_name": "shell.run_command", "args": {"command": "echo bench-loop"}},
                        # Simulate that the underlying tool calls were not failing; this is a logic-loop guard.
                        "tool_result": {"success": True, "output": "bench-loop"},
                    },
                }
            ],
        },
        "is_system_error": False,
    }
    ev = evaluate_attempt_result(exec_res=exec_res, anti_pattern_detected=True).to_dict()
    assert ev["category"] == "logic_path_error"
    assert ev["correction_intensity"] in {"high", "critical"}

