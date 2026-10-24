from __future__ import annotations

import json
from pathlib import Path

from app.harness import AgentHarness


def test_agent_harness_builds_dossier(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    summary = runtime_dir / "evidence" / "real-001" / "phase_01" / "execution_summary.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(
        json.dumps(
            {
                "workflow_id": "real-001",
                "phase_id": "phase_01",
                "terminal_state": "REJECTED",
                "primary_failure_type": "MISSING_REQUIRED_TEST",
                "secondary_failure_types": ["GRADER_FAILED"],
                "recovery_action": "replan_from_spec",
            }
        ),
        encoding="utf-8",
    )
    evidence = runtime_dir / "evidence" / "real-001" / "phase_01" / "evidence_phase_01_20260309120000000000.json"
    evidence.write_text(
        json.dumps(
            {
                "failed_required_tests": ["unit"],
                "required_test_failure_details": {
                    "unit": ["AttributeError: module 'app.main' has no attribute 'MockTemporalWorker'"]
                },
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "metrics" / "business_failure_monitor_report.json").write_text(
        json.dumps(
            {
                "matched_count": 1,
                "matched_ratio": 0.1,
                "triggered": True,
                "execution_remediation_snapshot": {
                    "triggered": True,
                    "top_stage": "planner",
                    "target_failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                },
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "metrics" / "business_failure_promotion_report.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "metrics" / "recovery_canary_report.json").write_text("{}", encoding="utf-8")
    hooks_dir = runtime_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "execution_ticket_20260401010101.json").write_text(
        json.dumps(
            {
                "type": "execution_remediation_required",
                "workflow_id": "real-001",
                "owner": "planner",
                "recommended_action": "retry_same_plan",
                "top_stage": "planner",
            }
        ),
        encoding="utf-8",
    )

    dossier = AgentHarness(runtime_dir=runtime_dir).build_dossier(workflow_id="real-001", phase_id="phase_01")
    markdown = dossier.to_markdown()
    assert "MISSING_REQUIRED_TEST" in markdown
    assert "replan_from_spec" in markdown
    assert "failed_required_tests" in markdown
    assert "MockTemporalWorker" in markdown
    assert "execution_remediation_required" in markdown
    assert "retry_same_plan" in markdown
    assert "execution_remediation_top_stage" in markdown
    assert "AGENT_SUBPROCESS_NONZERO_EXIT" in markdown
