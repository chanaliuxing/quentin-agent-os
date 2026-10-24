import json
from pathlib import Path

from app.evidence import EvidenceRecord, EvidenceStore
from app.metrics import build_policy_tuning_dataset, calibrate_auto_review_policy


def test_build_policy_tuning_dataset_counts_pass_and_reject(tmp_path: Path):
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
    store.record(
        EvidenceRecord(
            record_id="e2",
            run_id="run_02",
            phase_id="phase_01",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="b",
            head_sha="b",
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
    dataset = build_policy_tuning_dataset(runtime_dir=runtime_dir)
    assert dataset["sample_size"] == 2
    assert dataset["passed_count"] == 1
    assert dataset["rejected_count"] == 1


def test_calibrate_auto_review_policy_writes_policy_and_dataset(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    policy_file = tmp_path / "policies" / "auto_review_policy.json"
    policy_file.parent.mkdir(parents=True, exist_ok=True)
    policy_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "normal": {"confidence": {"approve": 0.9, "reject": 0.8}},
                    "strict": {"confidence": {"approve": 0.95, "reject": 0.85}},
                }
            }
        ),
        encoding="utf-8",
    )
    output_file = tmp_path / "policies" / "auto_review_policy.calibrated.json"
    result_file = calibrate_auto_review_policy(
        policy_file=policy_file,
        runtime_dir=runtime_dir,
        output_file=output_file,
    )
    assert result_file.exists()
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    assert payload["active_profile"] in {"normal", "strict"}
    dataset_file = runtime_dir / "metrics" / "policy_tuning_dataset.json"
    assert dataset_file.exists()
