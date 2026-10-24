from pathlib import Path

from app.evidence import EvidenceRecord, EvidenceStore


def test_evidence_store_records_and_reads_record(tmp_path):
    store = EvidenceStore(base_dir=tmp_path / "evidence")
    record = EvidenceRecord(
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
        failed_required_tests=[],
        required_test_outcomes={},
        required_test_failure_details={},
        grader_results={"contract_validator": "pass"},
        grader_details={},
        changed_files=["app/module_main/main.py"],
        first_failure_stage="",
        failure_signature="",
        owner_agent="",
    )

    path = store.record(record)
    loaded = store.read(path)

    assert path.exists()
    assert loaded.run_id == "run_01"
    assert loaded.acceptance_status == "passed"
    assert loaded.changed_files == ["app/module_main/main.py"]


def test_evidence_store_lists_records(tmp_path):
    store = EvidenceStore(base_dir=tmp_path / "evidence")
    record = EvidenceRecord(
        record_id="evidence_02",
        run_id="run_01",
        phase_id="phase_01",
        workflow_version="convergence-v1",
        module_ids=["module_main"],
        base_sha="abc1234",
        head_sha="abc1234",
        acceptance_status="rejected",
        test_status="failed",
        missing_required_tests=["integration"],
        failed_required_tests=[],
        required_test_outcomes={"integration": "missing"},
        required_test_failure_details={},
        grader_results={},
        grader_details={},
        changed_files=[],
        first_failure_stage="qa_output_missing",
        failure_signature="qa_output_missing:module_main",
        owner_agent="qa",
    )
    store.record(record)
    records = store.list_records("run_01", "phase_01")
    assert len(records) == 1
    assert Path(records[0]).name == "evidence_02.json"


def test_evidence_store_recent_records(tmp_path):
    store = EvidenceStore(base_dir=tmp_path / "evidence")
    for idx in range(3):
        store.record(
            EvidenceRecord(
                record_id=f"evidence_{idx}",
                run_id="run_01",
                phase_id="phase_01",
                workflow_version="convergence-v1",
                module_ids=["module_main"],
                base_sha="abc1234",
                head_sha="abc1234",
                acceptance_status="rejected",
                test_status="failed",
                missing_required_tests=[],
                failed_required_tests=["unit"],
                required_test_outcomes={"unit": "failed"},
                required_test_failure_details={"unit": ["AssertionError: expected 1 == 2"]},
                grader_results={},
                grader_details={},
                changed_files=[],
                first_failure_stage="qa_output_missing",
                failure_signature=f"qa_output_missing:{idx}",
                owner_agent="qa",
            )
        )
    recent = store.recent_records(limit=2)
    assert len(recent) == 2
