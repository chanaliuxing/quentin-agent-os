import json

from app.config import settings
from app.review import evaluate_auto_review
from app.review.auto_review import load_auto_review_policy


def test_evaluate_auto_review_rejects_when_missing_required_tests(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = tmp_path / "runtime" / "evidence" / "run" / "phase_01" / "evidence.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(
        json.dumps(
            {
                "acceptance_status": "rejected",
                "test_status": "failed",
                "missing_required_tests": ["integration"],
                "grader_results": {"contract_validator": "fail"},
                "first_failure_stage": "required_test_missing",
                "owner_agent": "qa",
            }
        ),
        encoding="utf-8",
    )
    (hooks_dir / "phase_01_human_review_required.json").write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "acceptance_status": "rejected",
                "failed_modules": ["module_main"],
                "evidence_file": str(evidence_file),
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_auto_review(phase_id="phase_01", hooks_dir=hooks_dir)
    assert result["decision"] == "rejected"
    assert any("MISSING_REQUIRED_TESTS" in item for item in result["risk_signals"])


def test_evaluate_auto_review_approves_clean_passed_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = tmp_path / "runtime" / "evidence" / "run" / "phase_01" / "evidence.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(
        json.dumps(
            {
                "acceptance_status": "passed",
                "test_status": "success",
                "missing_required_tests": [],
                "grader_results": {"contract_validator": "pass"},
                "first_failure_stage": "",
                "owner_agent": "",
            }
        ),
        encoding="utf-8",
    )
    (hooks_dir / "phase_01_human_review_required.json").write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "acceptance_status": "passed",
                "failed_modules": [],
                "evidence_file": str(evidence_file),
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_auto_review(phase_id="phase_01", hooks_dir=hooks_dir)
    assert result["decision"] == "approved"
    assert result["confidence"] >= 0.8
    assert result["policy_version"].startswith("auto_review_policy_v1")


def test_load_auto_review_policy_from_file(tmp_path):
    policy_file = tmp_path / "auto_review_policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "normal": {
                        "auto_approve_conditions": {"test_status": "success"},
                        "confidence": {"approve": 0.95, "reject": 0.7},
                    }
                },
                "structural_finding_codes": ["X_CODE"],
            }
        ),
        encoding="utf-8",
    )
    policy = load_auto_review_policy(policy_file=policy_file)
    assert policy["profiles"]["normal"]["confidence"]["approve"] == 0.95
    assert "X_CODE" in policy["structural_finding_codes"]


def test_load_auto_review_policy_profile_merge(tmp_path, monkeypatch):
    policy_file = tmp_path / "auto_review_policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "strict": {
                        "auto_approve_conditions": {"test_status": "success"},
                        "confidence": {"approve": 0.97, "reject": 0.86},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.review.auto_review.settings.auto_review_profile", "strict")
    policy = load_auto_review_policy(policy_file=policy_file)
    assert policy["profiles"]["strict"]["confidence"]["approve"] == 0.97


def test_load_auto_review_policy_prefers_file_active_profile_when_env_missing(tmp_path, monkeypatch):
    policy_file = tmp_path / "auto_review_policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "active_profile": "strict",
                "profiles": {
                    "normal": {"confidence": {"approve": 0.9, "reject": 0.8}},
                    "strict": {"confidence": {"approve": 0.97, "reject": 0.86}},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AUTO_REVIEW_PROFILE", raising=False)
    policy = load_auto_review_policy(policy_file=policy_file)
    assert policy["active_profile"] == "strict"
