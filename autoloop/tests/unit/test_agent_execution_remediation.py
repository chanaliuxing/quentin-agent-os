from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from app.metrics.agent_execution_remediation import (
    analyze_subprocess_nonzero_exit,
    create_execution_remediation_ticket_if_needed,
    write_execution_remediation_report,
)


def _write_run(
    *,
    runtime_dir: Path,
    run_id: str,
    primary_failure_type: str,
    stage: str = "",
    exit_code: int = 0,
    mtime: float = 0.0,
) -> None:
    phase_dir = runtime_dir / "evidence" / run_id / "phase_01"
    phase_dir.mkdir(parents=True, exist_ok=True)
    summary = phase_dir / "execution_summary.json"
    summary.write_text(
        json.dumps(
            {
                "workflow_id": run_id,
                "phase_id": "phase_01",
                "primary_failure_type": primary_failure_type,
                "terminal_state": "REJECTED",
                "recovery_action": "replan_from_spec",
            }
        ),
        encoding="utf-8",
    )
    evidence = phase_dir / "evidence_phase_01_0001.json"
    failure_events = []
    if primary_failure_type == "AGENT_SUBPROCESS_NONZERO_EXIT":
        failure_events = [
            {
                "stage": stage,
                "cause_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                "payload": {
                    "subprocess_detail": {
                        "exit_code": exit_code,
                        "execution_mode": "resume",
                        "session_source": "agent_spec",
                        "error_message": "boom",
                    }
                },
            }
        ]
    evidence.write_text(json.dumps({"failure_events": failure_events}), encoding="utf-8")
    if mtime > 0:
        os.utime(summary, (mtime, mtime))
        os.utime(evidence, (mtime, mtime))


def test_analyze_subprocess_nonzero_exit_triggers(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_run(
        runtime_dir=runtime_dir,
        run_id="real-001",
        primary_failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        stage="planner",
        exit_code=2,
        mtime=100.0,
    )
    _write_run(
        runtime_dir=runtime_dir,
        run_id="real-002",
        primary_failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        stage="planner",
        exit_code=2,
        mtime=200.0,
    )
    _write_run(
        runtime_dir=runtime_dir,
        run_id="real-003",
        primary_failure_type="MISSING_REQUIRED_TEST",
        mtime=300.0,
    )
    analysis = analyze_subprocess_nonzero_exit(runtime_dir=runtime_dir, window_size=20, min_count=2, min_ratio=0.2)
    assert analysis["triggered"] is True
    assert analysis["matched_count"] == 2
    assert analysis["top_stage"] == "planner"
    assert analysis["stage_distribution"]["planner"] == 2
    report_path = write_execution_remediation_report(analysis=analysis, runtime_dir=runtime_dir)
    assert report_path.exists()
    ticket_path = create_execution_remediation_ticket_if_needed(
        analysis=analysis,
        runtime_dir=runtime_dir,
        dedupe_hours=24,
    )
    assert ticket_path is not None
    payload = json.loads(ticket_path.read_text(encoding="utf-8"))
    assert payload["type"] == "execution_remediation_required"
    assert payload["recommended_action"] == "retry_same_plan"
    assert payload["owner"] == "planner"


def test_execution_remediation_dedupes_ticket_within_24h(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    hooks_dir = runtime_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    existing = hooks_dir / "execution_ticket_20260401010101.json"
    existing.write_text(
        json.dumps(
            {
                "created_at": (datetime.now() - timedelta(hours=1)).isoformat(),
                "target_failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                "normalized_signature": "agent_subprocess_nonzero_exit:planner",
            }
        ),
        encoding="utf-8",
    )
    analysis = {
        "triggered": True,
        "target_failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
        "top_stage": "planner",
        "window_size": 20,
        "matched_count": 2,
        "matched_ratio": 0.2,
        "latest_match": {
            "workflow_id": "real-020",
            "phase_id": "phase_01",
            "summary_file": str(runtime_dir / "evidence" / "real-020" / "phase_01" / "execution_summary.json"),
            "stage": "planner",
            "exit_code": 2,
            "execution_mode": "resume",
            "session_source": "agent_spec",
            "error_message": "boom",
        },
        "stage_distribution": {"planner": 2},
    }
    ticket_path = create_execution_remediation_ticket_if_needed(
        analysis=analysis,
        runtime_dir=runtime_dir,
        dedupe_hours=24,
    )
    assert ticket_path is None


def test_analyze_subprocess_nonzero_exit_ignores_non_real_by_default(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_run(
        runtime_dir=runtime_dir,
        run_id="reg-001",
        primary_failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        stage="planner",
        exit_code=2,
        mtime=100.0,
    )
    _write_run(
        runtime_dir=runtime_dir,
        run_id="reg-002",
        primary_failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        stage="planner",
        exit_code=2,
        mtime=200.0,
    )
    analysis = analyze_subprocess_nonzero_exit(runtime_dir=runtime_dir, window_size=20, min_count=2, min_ratio=0.2)
    assert analysis["evaluated_runs"] == 0
    assert analysis["triggered"] is False
