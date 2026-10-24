from __future__ import annotations

from quentin.cognitive.self_awareness import SelfAwarenessEngine


def test_self_awareness_detects_context_overflow_reason() -> None:
    engine = SelfAwarenessEngine()
    snapshot = engine.observe_attempt(
        exec_result={
            "raw": {"error": "Request failed: maximum context length exceeded (413)"},
            "is_system_error": False,
        },
        metrics={"total_attempts": 3, "error_attempts": 2},
        degrade_mode=False,
        self_programming_enabled=True,
    )
    assert snapshot.status == "warning"
    assert snapshot.failover_reason == "context_overflow"
    assert "trigger_compaction_and_trim_context" in snapshot.suggested_actions


def test_self_awareness_tracks_consecutive_system_errors() -> None:
    engine = SelfAwarenessEngine()
    first = engine.observe_attempt(
        exec_result={"raw": {"error": "timeout"}, "is_system_error": True},
        metrics={"total_attempts": 1, "error_attempts": 1},
        degrade_mode=False,
        self_programming_enabled=True,
    )
    second = engine.observe_attempt(
        exec_result={"raw": {"error": "timeout"}, "is_system_error": True},
        metrics={"total_attempts": 2, "error_attempts": 2},
        degrade_mode=True,
        self_programming_enabled=False,
    )
    assert first.consecutive_system_errors == 1
    assert second.consecutive_system_errors == 2
    assert second.status == "critical"
    assert "escalate_to_reflection_or_abort" in second.suggested_actions


def test_self_awareness_detects_antipattern_from_feedback_tail() -> None:
    engine = SelfAwarenessEngine()
    snapshot = engine.observe_attempt(
        exec_result={
            "final_output": "",
            "raw": {
                "steps": [
                    {
                        "result": {
                            "status": "error",
                            "feedback_tail": [
                                {
                                    "tool_call": {
                                        "tool_name": "shell.run_command",
                                        "args": {"command": "cd quentin/infra/tools && nano ai_cli.py"},
                                    },
                                    "tool_result": {
                                        "status": "error",
                                        "error": "Interactive command 'nano' detected and blocked",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            "is_system_error": False,
        },
        metrics={"total_attempts": 2, "error_attempts": 1},
        degrade_mode=False,
        self_programming_enabled=True,
    )
    assert snapshot.anti_pattern_reason == "interactive_editor_command"
    assert "switch_to_fs_read_and_write_flow" in snapshot.suggested_actions


def test_self_awareness_counts_consecutive_no_progress() -> None:
    engine = SelfAwarenessEngine()
    one = engine.observe_attempt(
        exec_result={
            "final_output": "",
            "raw": {"steps": [{"result": {"tool_result": {"status": "ok"}}}]},
            "is_system_error": False,
        },
        metrics={"total_attempts": 1, "error_attempts": 0},
        degrade_mode=False,
        self_programming_enabled=True,
    )
    two = engine.observe_attempt(
        exec_result={
            "final_output": "",
            "raw": {"steps": [{"result": {"feedback_tail": [{"tool_call": {"tool_name": "fs.read_file"}}]}}]},
            "is_system_error": False,
        },
        metrics={"total_attempts": 2, "error_attempts": 1},
        degrade_mode=False,
        self_programming_enabled=True,
    )
    assert one.consecutive_no_progress == 1
    assert two.consecutive_no_progress == 2
    assert two.status in {"warning", "critical"}
