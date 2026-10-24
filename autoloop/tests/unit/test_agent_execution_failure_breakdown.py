import json
from pathlib import Path

from app.metrics.agent_execution_failure_breakdown import (
    build_agent_execution_failure_breakdown,
    write_agent_execution_failure_breakdown_report,
)


def _write_summary(
    runtime_dir: Path,
    workflow_id: str,
    primary_failure_type: str,
    recovery_action: str = "replan_from_spec",
) -> None:
    target = runtime_dir / "evidence" / workflow_id / "phase_01" / "execution_summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "phase_id": "phase_01",
                "primary_failure_type": primary_failure_type,
                "terminal_state": "REJECTED",
                "recovery_action": recovery_action,
            }
        ),
        encoding="utf-8",
    )


def _write_evidence_with_subprocess_detail(
    runtime_dir: Path,
    workflow_id: str,
    *,
    stage: str,
    exit_code: int,
    execution_mode: str = "resume",
) -> None:
    target = runtime_dir / "evidence" / workflow_id / "phase_01" / "evidence_phase_01_0001.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "failure_events": [
                    {
                        "stage": stage,
                        "cause_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                        "payload": {
                            "subprocess_detail": {
                                "exit_code": exit_code,
                                "execution_mode": execution_mode,
                                "session_source": "agent_spec",
                                "error_message": "process exited",
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_build_agent_execution_failure_breakdown_counts_subtypes(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "real-1", "AGENT_SUBPROCESS_NONZERO_EXIT")
    _write_summary(runtime_dir, "real-2", "AGENT_EXECUTION_FAILED")
    _write_summary(runtime_dir, "real-3", "GLOBAL_TIMEOUT")
    report = build_agent_execution_failure_breakdown(runtime_dir=runtime_dir, window_size=20, real_only=True)
    assert report["agent_execution_failures_in_window"] == 2
    assert report["distribution"]["AGENT_SUBPROCESS_NONZERO_EXIT"] == 1
    assert report["distribution"]["AGENT_EXECUTION_FAILED"] == 1
    assert report["agent_execution_failed_parent_ratio"] == 0.5
    assert "trend_vs_previous_window" in report
    assert "top2_subtype_recovery_match" in report


def test_write_agent_execution_failure_breakdown_report(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "real-1", "AGENT_RESULT_PARSE_FAILED")
    path = write_agent_execution_failure_breakdown_report(runtime_dir=runtime_dir, window_size=20, real_only=True)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["distribution"]["AGENT_RESULT_PARSE_FAILED"] == 1


def test_top2_recovery_match_rate(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "real-1", "AGENT_OUTPUT_MISSING", recovery_action="replan_from_spec")
    _write_summary(runtime_dir, "real-2", "AGENT_RESULT_PARSE_FAILED", recovery_action="replan_from_spec")
    report = build_agent_execution_failure_breakdown(runtime_dir=runtime_dir, window_size=20, real_only=True)
    assert report["top2_subtype_recovery_match"]["evaluated"] == 2
    assert report["top2_subtype_recovery_match"]["match_rate"] == 1.0


def test_subprocess_nonzero_exit_breakdown(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "real-1", "AGENT_SUBPROCESS_NONZERO_EXIT")
    _write_evidence_with_subprocess_detail(
        runtime_dir,
        "real-1",
        stage="dev",
        exit_code=2,
    )
    report = build_agent_execution_failure_breakdown(runtime_dir=runtime_dir, window_size=20, real_only=True)
    breakdown = report["subprocess_nonzero_exit_breakdown"]
    assert breakdown["count"] == 1
    assert breakdown["by_exit_code"]["2"] == 1
    assert breakdown["by_stage"]["dev"] == 1
    assert breakdown["examples"][0]["execution_mode"] == "resume"
