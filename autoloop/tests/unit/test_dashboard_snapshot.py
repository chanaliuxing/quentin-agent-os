from pathlib import Path

from app.dashboard import build_dashboard_snapshot
from app.evidence import EvidenceRecord, EvidenceStore


def test_build_dashboard_snapshot_counts_files(tmp_path: Path):
    phases_dir = tmp_path / "phases" / "phase_01"
    phases_dir.mkdir(parents=True, exist_ok=True)
    (phases_dir / "phase_report.md").write_text("report", encoding="utf-8")

    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "phase_01_dev_done.json").write_text("{}", encoding="utf-8")
    (hooks_dir / "phase_01_human_review_required.json").write_text(
        '{"phase_id":"phase_01","acceptance_status":"rejected"}',
        encoding="utf-8",
    )
    evidence_store = EvidenceStore(tmp_path / "runtime" / "evidence")
    evidence_store.record(
        EvidenceRecord(
            record_id="evidence_01",
            run_id="run_01",
            phase_id="phase_01",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="abc1234",
            head_sha="abc1234",
            acceptance_status="passed",
            test_status="success",
            missing_required_tests=[],
            grader_results={"contract_validator": "pass"},
            changed_files=["app/module_main/main.py"],
            first_failure_stage="",
            failure_signature="",
            owner_agent="",
            trace_id="run_01:phase_01:0",
        )
    )
    evidence_store.record(
        EvidenceRecord(
            record_id="evidence_02",
            run_id="run_02",
            phase_id="phase_01",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="abc1234",
            head_sha="abc1234",
            acceptance_status="rejected",
            test_status="failed",
            missing_required_tests=[],
            grader_results={"contract_validator": "fail"},
            changed_files=[],
            first_failure_stage="dev_contract_failed",
            failure_type="MISSING_DEV_ARTIFACT",
            failure_signature="dev_contract_failed:module_main",
            owner_agent="dev",
            missing_artifacts=["app/main/artifacts/phase_01_result.json"],
            trace_id="run_02:phase_01:0",
        )
    )

    snapshot = build_dashboard_snapshot(tmp_path)
    assert snapshot["phase_count"] == 1
    assert snapshot["hook_count"] == 2
    assert snapshot["evidence_count"] == 2
    assert snapshot["human_review_count"] == 1
    assert len(snapshot["phase_reports"]) == 1
    assert len(snapshot["hooks"]) == 2
    assert len(snapshot["human_review_hooks"]) == 1
    assert len(snapshot["evidence_files"]) == 2
    assert snapshot["latest_evidence"] is not None
    assert snapshot["latest_evidence"]["acceptance_status"] in {"passed", "rejected"}
    assert "latest_failure_stage" in snapshot
    assert "latest_failure_signature" in snapshot
    assert "latest_failure_owner" in snapshot
    assert snapshot["latest_trace_id"] in {"run_01:phase_01:0", "run_02:phase_01:0"}
    assert "recent_failure_signatures" in snapshot
    assert "failure_taxonomy" in snapshot
    assert snapshot["failure_taxonomy"]["sample_size"] == 2
    assert snapshot["failure_taxonomy"]["failure_type_distribution"]["MISSING_DEV_ARTIFACT"] == 1
