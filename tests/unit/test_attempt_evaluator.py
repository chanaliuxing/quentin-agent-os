from __future__ import annotations

from quentin.cognitive.attempt_evaluator import evaluate_attempt_result


def test_evaluate_attempt_result_detects_tool_execution_error() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "failed",
            "raw": {
                "success": False,
                "steps": [
                    {
                        "success": False,
                        "error": "permission denied",
                        "result": {"tool_result": {"success": False}},
                    }
                ],
            },
        }
    )
    assert res.category in {"tool_execution_error", "mixed"}
    assert res.correction_intensity in {"medium", "high"}
    assert res.error_subcategory in {"generic_tool_error", "filesystem_generic_error", "shell_permission_denied"}


def test_evaluate_attempt_result_detects_logic_path_error() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "loop_detected: injecting_breakout_instruction",
            "raw": {
                "success": False,
                "steps": [
                    {
                        "success": True,
                        "result": {"call_tool": {"tool_name": "fs.read_file", "arguments": {"path": "x"}}},
                    }
                ],
            },
        },
        anti_pattern_detected=True,
    )
    assert res.category in {"logic_path_error", "mixed"}
    assert res.correction_intensity in {"high", "critical"}


def test_evaluate_attempt_result_detects_system_error() -> None:
    res = evaluate_attempt_result(exec_res={"is_system_error": True, "raw": {"success": False}})
    assert res.category == "system_error"
    assert res.correction_intensity == "critical"
    assert res.retry_cost >= 2.0


def test_evaluate_attempt_result_distinguishes_model_syntax_error() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "json parse failed",
            "raw": {"success": False, "error": "JSONDecodeError: invalid json"},
        }
    )
    assert res.category == "model_syntax_error"
    assert res.error_origin == "model"
    assert res.retry_cost <= 1.25


def test_evaluate_attempt_result_distinguishes_environment_timeout_error() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "tool timeout",
            "raw": {"success": False, "error": "TimeoutError: operation timed out"},
        }
    )
    assert res.category == "environment_timeout_error"
    assert res.error_origin == "environment"
    assert res.retry_cost >= 2.0


def test_evaluate_attempt_result_sets_shell_permission_subcategory() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "shell failed",
            "raw": {
                "success": False,
                "steps": [
                    {
                        "result": {
                            "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "rm /x"}},
                            "error": "permission denied",
                        }
                    }
                ],
            },
        }
    )
    assert res.error_subcategory == "shell_permission_denied"


def test_evaluate_attempt_result_escalates_plan_execution_misalignment() -> None:
    res = evaluate_attempt_result(
        exec_res={
            "is_system_error": False,
            "actions_summary": "alignment mismatch",
            "raw": {
                "success": False,
                "steps": [
                    {
                        "result": {
                            "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "cat x.py"}},
                            "feedback_tail": [
                                {"type": "tool_alignment_violation", "reason": "plan_execution_misalignment"}
                            ],
                        }
                    }
                ],
            },
        }
    )
    assert res.category == "plan_execution_misalignment"
    assert res.correction_intensity == "high"
    assert res.retry_cost >= 1.75
