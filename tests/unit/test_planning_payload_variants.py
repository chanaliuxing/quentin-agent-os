from __future__ import annotations

from quentin.cognitive.planning_payload_variants import derive_planner_payload_variant


def test_planner_payload_variant_shell_retry_timeout() -> None:
    out = derive_planner_payload_variant(
        context={
            "planner_lifecycle_payload": {"stage": "retry", "attempt_band": "mid"},
            "last_attempt_evaluation": {
                "category": "environment_timeout_error",
                "error_subcategory": "shell_command_not_found",
            },
            "last_exec_result": {
                "raw": {
                    "steps": [
                        {
                            "result": {
                                "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "ls"}},
                            }
                        }
                    ]
                }
            },
        }
    )
    assert out.get("tool_family") == "shell"
    assert "variant_id" in out
    assert "required_prechecks" in out
    assert out.get("attempt_band") == "mid"
    assert "shell_diag" in list(out.get("required_prechecks") or [])
    assert "command_exists_probe" in list(out.get("required_prechecks") or [])


def test_planner_payload_variant_browser_stuck_model_syntax() -> None:
    out = derive_planner_payload_variant(
        context={
            "planner_lifecycle_payload": {"stage": "stuck"},
            "last_attempt_evaluation": {"category": "model_syntax_error"},
            "last_exec_result": {
                "raw": {
                    "steps": [
                        {"result": {"call_tool": {"tool_name": "browser.click", "arguments": {"selector": "#x"}}}}
                    ]
                }
            },
        }
    )
    reqs = list(out.get("required_prechecks") or [])
    assert out.get("tool_family") == "browser"
    assert "browser_state_probe" in reqs
    assert "selector_probe" in reqs
    assert "schema_guard" in reqs


def test_planner_payload_variant_late_band_requires_progress_sync() -> None:
    out = derive_planner_payload_variant(
        context={
            "planner_lifecycle_payload": {"stage": "retry", "attempt_band": "late"},
            "last_attempt_evaluation": {"category": "tool_execution_error"},
            "last_exec_result": {
                "raw": {
                    "steps": [
                        {"result": {"call_tool": {"tool_name": "fs.write_file", "arguments": {"path": "a"}}}}
                    ]
                }
            },
        }
    )
    reqs = list(out.get("required_prechecks") or [])
    assert out.get("attempt_band") == "late"
    assert "progress_sync" in reqs


def test_planner_payload_variant_includes_tool_alignment_checks_for_misalignment() -> None:
    out = derive_planner_payload_variant(
        context={
            "planner_lifecycle_payload": {"stage": "retry", "attempt_band": "mid"},
            "last_attempt_evaluation": {
                "category": "tool_execution_error",
                "error_subcategory": "plan_execution_misalignment",
            },
            "last_exec_result": {
                "raw": {
                    "steps": [
                        {
                            "result": {
                                "call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "cat x.py"}},
                            }
                        }
                    ]
                }
            },
        }
    )
    reqs = list(out.get("required_prechecks") or [])
    assert "tool_alignment_check" in reqs
