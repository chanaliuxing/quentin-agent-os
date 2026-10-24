import json

import pytest

from app.config import settings
from app.review import evaluate_auto_review


@pytest.mark.parametrize(
    "name,evidence_payload,hook_payload,expected_decision",
    [
        (
            "missing_required_tests",
            {
                "acceptance_status": "rejected",
                "test_status": "failed",
                "missing_required_tests": ["integration"],
                "grader_results": {"contract_validator": "fail"},
                "first_failure_stage": "required_test_missing",
                "owner_agent": "qa",
            },
            {"acceptance_status": "rejected", "failed_modules": ["module_main"]},
            "rejected",
        ),
        (
            "structural_reviewer_risk",
            {
                "acceptance_status": "rejected",
                "test_status": "failed",
                "missing_required_tests": [],
                "grader_results": {"contract_validator": "pass"},
                "first_failure_stage": "review_gate_rejected",
                "owner_agent": "reviewer",
            },
            {"acceptance_status": "rejected", "failed_modules": ["module_main"]},
            "rejected",
        ),
        (
            "clean_pass",
            {
                "acceptance_status": "passed",
                "test_status": "success",
                "missing_required_tests": [],
                "grader_results": {"contract_validator": "pass"},
                "first_failure_stage": "",
                "owner_agent": "",
            },
            {"acceptance_status": "passed", "failed_modules": []},
            "approved",
        ),
    ],
)
def test_auto_review_replay_pack(monkeypatch, tmp_path, name, evidence_payload, hook_payload, expected_decision):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = tmp_path / "runtime" / "evidence" / "run_01" / "phase_01" / f"evidence_{name}.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(json.dumps(evidence_payload), encoding="utf-8")
    hook_payload = dict(hook_payload)
    hook_payload["phase_id"] = "phase_01"
    hook_payload["evidence_file"] = str(evidence_file)
    (hooks_dir / "phase_01_human_review_required.json").write_text(
        json.dumps(hook_payload),
        encoding="utf-8",
    )

    if name == "structural_reviewer_risk":
        phase_results_dir = tmp_path / "phases" / "phase_01" / "results"
        phase_results_dir.mkdir(parents=True, exist_ok=True)
        (phase_results_dir / "module_main_reviewer.md").write_text(
            json.dumps(
                {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-07T00:00:00",
                    "module_name": "module_main",
                    "verdict": "needs_revision",
                    "findings": ["path policy mismatch"],
                    "finding_codes": ["PATH_CONFLICT"],
                }
            ),
            encoding="utf-8",
        )

    result = evaluate_auto_review(phase_id="phase_01", hooks_dir=hooks_dir)
    assert result["decision"] == expected_decision
