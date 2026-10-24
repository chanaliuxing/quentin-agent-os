from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from app.metrics.business_failure_monitor import (
    analyze_rolling_business_failure,
    create_taxonomy_ticket_if_needed,
    write_business_failure_monitor_report,
)


def _write_summary(
    *,
    runtime_dir: Path,
    run_id: str,
    phase_id: str,
    primary_failure_type: str,
    first_failure_stage: str = "",
    failure_signature: str = "",
    failure_events: list[dict] | None = None,
    mtime: float = 0.0,
) -> Path:
    path = runtime_dir / "evidence" / run_id / phase_id / "execution_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "workflow_id": run_id,
        "phase_id": phase_id,
        "primary_failure_type": primary_failure_type,
        "first_failure_stage": first_failure_stage,
        "failure_signature": failure_signature,
        "terminal_state": "REJECTED",
        "recovery_action": "taxonomy_review_required",
        "failure_events": failure_events or [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if mtime > 0:
        os.utime(path, (mtime, mtime))
    return path


def test_monitor_triggers_and_creates_taxonomy_ticket(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(
        runtime_dir=runtime_dir,
        run_id="real-001",
        phase_id="phase_01",
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        first_failure_stage="unclassified_failure",
        failure_signature="sig-a",
        mtime=100.0,
    )
    _write_summary(
        runtime_dir=runtime_dir,
        run_id="real-002",
        phase_id="phase_01",
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        first_failure_stage="unclassified_failure",
        failure_signature="sig-a",
        mtime=200.0,
    )
    _write_summary(
        runtime_dir=runtime_dir,
        run_id="real-003",
        phase_id="phase_01",
        primary_failure_type="MISSING_REQUIRED_TEST",
        mtime=300.0,
    )

    analysis = analyze_rolling_business_failure(runtime_dir=runtime_dir, window_size=20, min_count=2, min_ratio=0.05)
    assert analysis["triggered"] is True
    assert analysis["matched_count"] == 2
    report_path = write_business_failure_monitor_report(analysis=analysis, runtime_dir=runtime_dir)
    assert report_path.exists()
    ticket_path = create_taxonomy_ticket_if_needed(analysis=analysis, runtime_dir=runtime_dir, dedupe_hours=24)
    assert ticket_path is not None
    payload = json.loads(ticket_path.read_text(encoding="utf-8"))
    assert payload["type"] == "taxonomy_review_required"
    assert payload["target_failure_type"] == "BUSINESS_REJECTION_UNMAPPED"
    assert payload["normalized_signature"] == "sig-a"


def test_monitor_dedupes_ticket_within_24h(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    hooks_dir = runtime_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    existing = hooks_dir / "taxonomy_ticket_20260308010101.json"
    existing_created_at = (datetime.now() - timedelta(hours=1)).isoformat()
    existing.write_text(
        json.dumps(
            {
                "created_at": existing_created_at,
                "target_failure_type": "BUSINESS_REJECTION_UNMAPPED",
                "normalized_signature": "sig-b",
            }
        ),
        encoding="utf-8",
    )
    analysis = {
        "triggered": True,
        "target_failure_type": "BUSINESS_REJECTION_UNMAPPED",
        "latest_match": {
            "failure_signature": "sig-b",
            "workflow_id": "real-010",
            "phase_id": "phase_01",
            "primary_failure_type": "BUSINESS_REJECTION_UNMAPPED",
            "terminal_state": "REJECTED",
            "summary_file": str(runtime_dir / "evidence" / "real-010" / "phase_01" / "execution_summary.json"),
            "failure_events": [],
        },
        "window_size": 20,
        "matched_count": 2,
        "matched_ratio": 0.1,
    }
    ticket_path = create_taxonomy_ticket_if_needed(analysis=analysis, runtime_dir=runtime_dir, dedupe_hours=24)
    assert ticket_path is None


def test_monitor_ignores_non_real_runs_by_default(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(
        runtime_dir=runtime_dir,
        run_id="reg-001",
        phase_id="phase_01",
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        failure_signature="sig-c",
        mtime=100.0,
    )
    _write_summary(
        runtime_dir=runtime_dir,
        run_id="reg-002",
        phase_id="phase_01",
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        failure_signature="sig-c",
        mtime=200.0,
    )
    analysis = analyze_rolling_business_failure(runtime_dir=runtime_dir, window_size=20, min_count=2, min_ratio=0.05)
    assert analysis["evaluated_runs"] == 0
    assert analysis["triggered"] is False


def test_write_business_failure_monitor_report_includes_execution_remediation_snapshot(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    metrics_dir = runtime_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "agent_execution_remediation_report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-01T00:00:00",
                "target_failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                "top_stage": "planner",
                "triggered": True,
            }
        ),
        encoding="utf-8",
    )
    analysis = {
        "generated_at": "2026-04-01T00:00:01",
        "target_failure_type": "BUSINESS_REJECTION_UNMAPPED",
        "triggered": False,
    }
    report_path = write_business_failure_monitor_report(analysis=analysis, runtime_dir=runtime_dir)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert "execution_remediation_snapshot" in payload
    assert payload["execution_remediation_snapshot"]["top_stage"] == "planner"
