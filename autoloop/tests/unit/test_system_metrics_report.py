from pathlib import Path

from app.evidence import EvidenceRecord, EvidenceStore
from app.metrics import build_system_hardening_report, write_system_hardening_report


def test_build_system_hardening_report_computes_rates(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    store = EvidenceStore(runtime_dir / "evidence")
    store.record(
        EvidenceRecord(
            record_id="e1",
            run_id="run_01",
            phase_id="phase_01",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="a",
            head_sha="a",
            acceptance_status="rejected",
            test_status="failed",
            missing_required_tests=[],
            grader_results={},
            changed_files=[],
            first_failure_stage="dev_output_missing",
            failure_signature="dev_output_missing:module_main",
            owner_agent="dev",
        )
    )
    store.record(
        EvidenceRecord(
            record_id="e2",
            run_id="run_01",
            phase_id="phase_02",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="a",
            head_sha="a",
            acceptance_status="passed",
            test_status="success",
            missing_required_tests=[],
            grader_results={},
            changed_files=[],
            first_failure_stage="",
            failure_signature="",
            owner_agent="",
        )
    )

    report = build_system_hardening_report(runtime_dir=runtime_dir)
    assert report["sample_size"] == 2
    assert report["auto_resume_success_count"] == 1
    assert "failure_owner_distribution" in report
    assert "failure_stage_distribution" in report
    assert "failure_type_distribution" in report
    assert "unclassified_business_failure_count" in report
    assert "unclassified_business_stage_distribution" in report
    assert "unclassified_business_top_signatures" in report
    assert "missing_artifact_distribution" in report
    assert "acceptance_distribution" in report
    assert "runner_health" in report


def test_write_system_hardening_report_writes_file(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    path = write_system_hardening_report(runtime_dir=runtime_dir)
    assert path.exists()


def test_write_system_hardening_report_contains_delta_and_history(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    first = write_system_hardening_report(runtime_dir=runtime_dir)
    assert first.exists()
    second = write_system_hardening_report(runtime_dir=runtime_dir)
    assert second.exists()
    payload = second.read_text(encoding="utf-8")
    assert "delta_vs_previous" in payload
    history_dir = runtime_dir / "metrics" / "history"
    assert history_dir.exists()
    assert any(history_dir.glob("system_hardening_report_*.json"))
