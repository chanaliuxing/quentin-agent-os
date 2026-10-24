from __future__ import annotations

from quentin.cognitive.tool_error_subtypes import classify_tool_error_subtype


def test_classify_tool_error_subtype_shell_permission_denied() -> None:
    fam, sub = classify_tool_error_subtype(
        last_exec_result={
            "raw": {
                "steps": [
                    {
                        "result": {
                            "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "rm x"}},
                            "error": "permission denied",
                        }
                    }
                ]
            }
        }
    )
    assert fam == "shell"
    assert sub == "shell_permission_denied"


def test_classify_tool_error_subtype_browser_selector_not_found() -> None:
    fam, sub = classify_tool_error_subtype(
        last_exec_result={
            "raw": {
                "steps": [
                    {
                        "result": {
                            "call_tool": {"tool_name": "browser.click", "arguments": {"selector": "#x"}},
                            "error": "selector not found",
                        }
                    }
                ]
            }
        }
    )
    assert fam == "browser"
    assert sub == "browser_selector_not_found"


def test_classify_tool_error_subtype_plan_execution_misalignment() -> None:
    fam, sub = classify_tool_error_subtype(
        last_exec_result={
            "raw": {
                "steps": [
                    {
                        "result": {
                            "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "cat x.py"}},
                            "feedback_tail": [
                                {"type": "tool_alignment_violation", "reason": "plan_execution_misalignment"}
                            ],
                        }
                    }
                ]
            }
        }
    )
    assert fam == "shell"
    assert sub == "plan_execution_misalignment"
