import json
import os
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from app.config import settings
from app.evidence import EvidenceRecord, EvidenceStore
from app.main import (
    app,
    _apply_runner_health_delta_gate,
    _collect_preflight_issues,
    _normalize_project_root,
    _normalize_runner_configuration,
)


def test_normalize_project_root_uses_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path / "wrong_root")
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        _normalize_project_root()
        assert settings.project_root.resolve() == tmp_path.resolve()
    finally:
        os.chdir(original_cwd)


def test_normalize_runner_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    monkeypatch.setattr(settings, "codex_session_id", "")
    monkeypatch.setattr(settings, "codex_timeout_profile", "codex_fast")
    monkeypatch.setattr(settings, "codex_fast_attempt_timeout_seconds", 45)
    monkeypatch.setattr(settings, "codex_fast_total_timeout_seconds", 180)
    monkeypatch.setattr(settings, "codex_attempt_timeout_seconds", 999)
    monkeypatch.setattr(settings, "agent_total_timeout_seconds", 999)
    _normalize_runner_configuration()
    assert settings.agent_runner_type == "codex"
    assert settings.codex_attempt_timeout_seconds == 45
    assert settings.agent_total_timeout_seconds == 180


def test_normalize_runner_respects_custom_codex_profile(monkeypatch):
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    monkeypatch.setattr(settings, "codex_timeout_profile", "custom")
    monkeypatch.setattr(settings, "codex_attempt_timeout_seconds", 73)
    monkeypatch.setattr(settings, "agent_total_timeout_seconds", 333)
    _normalize_runner_configuration()
    assert settings.codex_attempt_timeout_seconds == 73
    assert settings.agent_total_timeout_seconds == 333


def test_run_fails_fast_when_prd_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "execution_profile", "dev")
    monkeypatch.setattr(settings, "agent_runner_type", "mock")
    runner = CliRunner()
    result = runner.invoke(app, ["run", "missing_prd.md", "--mode", "graph"])
    assert result.exit_code == 1
    assert "PRD file not found" in result.stdout


def test_prod_profile_rejects_mock_runner(monkeypatch, tmp_path):
    prd_file = tmp_path / "prd.md"
    prd_file.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "execution_profile", "dev")
    monkeypatch.setattr(settings, "agent_runner_type", "mock")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(prd_file), "--mode", "graph", "--profile", "prod"],
    )
    assert result.exit_code == 2
    assert "prod profile forbids mock runner" in result.stdout


def test_prod_profile_temporal_requires_real_temporal(monkeypatch, tmp_path):
    prd_file = tmp_path / "prd.md"
    prd_file.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "execution_profile", "dev")
    monkeypatch.setattr(settings, "agent_runner_type", "gemini")
    monkeypatch.setattr(settings, "gemini_session_id", "session-ok")
    monkeypatch.setattr(settings, "temporal_mock_mode", True)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(prd_file), "--mode", "temporal", "--profile", "prod"],
    )
    assert result.exit_code == 2
    assert "prod profile requires real Temporal mode" in result.stdout


def test_collect_preflight_issues_prod_runner_missing_session(monkeypatch, tmp_path):
    prd_file = tmp_path / "prd.md"
    prd_file.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(settings, "execution_profile", "prod")
    monkeypatch.setattr(settings, "agent_runner_type", "claude")
    monkeypatch.setattr(settings, "claude_session_id", "")
    issues = _collect_preflight_issues("graph", str(prd_file))
    assert any("requires session id" in issue for issue in issues)


def test_doctor_fails_on_invalid_preflight(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "execution_profile", "prod")
    monkeypatch.setattr(settings, "agent_runner_type", "mock")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", str(tmp_path / "missing.md"), "--mode", "graph"])
    assert result.exit_code == 1
    assert "Preflight checks failed" in result.stdout


def test_doctor_shows_latest_evidence_summary(monkeypatch, tmp_path):
    prd_file = tmp_path / "prd.md"
    prd_file.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "execution_profile", "dev")
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    monkeypatch.setattr(settings, "codex_session_id", "")
    settings.ensure_dirs()

    evidence_store = EvidenceStore(settings.runtime_dir / "evidence")
    evidence_store.record(
        EvidenceRecord(
            record_id=f"evidence_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            run_id="run_01",
            phase_id="phase_01",
            workflow_version="convergence-v1",
            module_ids=["module_main"],
            base_sha="abc1234",
            head_sha="abc1234",
            acceptance_status="rejected",
            test_status="failed",
            missing_required_tests=["integration"],
            grader_results={"contract_validator": "fail"},
            changed_files=["README.md"],
            first_failure_stage="required_test_missing",
            failure_signature="required_test_missing:integration",
            owner_agent="qa",
        )
    )

    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["doctor", str(prd_file), "--mode", "graph"])
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Latest Evidence:" in result.stdout
    assert "Evidence Acceptance:" in result.stdout
    assert "First Failure Stage:" in result.stdout
    assert "Failure Owner:" in result.stdout
    assert "Missing Required Tests:" in result.stdout


def test_reviews_command_lists_pending_human_review_hooks(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    settings.ensure_dirs()
    hook_file = settings.hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        '{"phase_id":"phase_01","acceptance_status":"rejected","failed_modules":["module_main"]}',
        encoding="utf-8",
    )
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["reviews"])
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Human Review Queue" in result.stdout
    assert "phase_01" in result.stdout


def test_review_command_resolves_hook_without_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    settings.ensure_dirs()
    hook_file = settings.hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        '{"phase_id":"phase_01","project_id":"autoloop-project","prd_path":"/tmp/prd.md"}',
        encoding="utf-8",
    )
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["review", "--phase-id", "phase_01", "--decision", "approved", "--no-resume"],
        )
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Resolved human review for phase_01" in result.stdout
    assert (settings.hooks_dir / "phase_01_human_review_resolution.json").exists()


def test_auto_review_command_resolves_hook_without_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    evidence_file = settings.runtime_dir / "evidence" / "run_01" / "phase_01" / "evidence_01.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(
        '{"acceptance_status":"rejected","test_status":"failed","missing_required_tests":["integration"],"grader_results":{"contract_validator":"fail"}}',
        encoding="utf-8",
    )
    hook_file = settings.hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "acceptance_status": "rejected",
                "failed_modules": ["module_main"],
                "evidence_file": str(evidence_file),
                "project_id": "autoloop-project",
                "prd_path": "/tmp/prd.md",
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["auto-review", "--phase-id", "phase_01", "--no-resume"],
        )
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Auto review decision:" in result.stdout
    assert (settings.hooks_dir / "phase_01_human_review_resolution.json").exists()


def test_system_metrics_report_command_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["system-metrics-report"])
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "System hardening report written" in result.stdout
    assert (settings.runtime_dir / "metrics" / "system_hardening_report.json").exists()


def test_calibrate_auto_review_policy_command_writes_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    policy_file = tmp_path / "policies" / "auto_review_policy.json"
    policy_file.parent.mkdir(parents=True, exist_ok=True)
    policy_file.write_text(
        '{"profiles":{"normal":{"confidence":{"approve":0.9,"reject":0.8}},"strict":{"confidence":{"approve":0.95,"reject":0.85}}}}',
        encoding="utf-8",
    )
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["calibrate-auto-review-policy", "--apply-to-default"],
        )
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Calibrated policy written" in result.stdout
    assert (tmp_path / "policies" / "auto_review_policy.calibrated.json").exists()
    assert (settings.runtime_dir / "metrics" / "policy_tuning_dataset.json").exists()


def test_governance_review_command_resolves_hook_without_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    hook_file = settings.hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "acceptance_status": "rejected",
                "failed_modules": ["module_main"],
                "project_id": "autoloop-project",
                "prd_path": "/tmp/prd.md",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.main.evaluate_governance_review",
        lambda phase_id="": {
            "decision": "rejected",
            "confidence": 0.85,
            "notes": "governance reject",
            "risk_signals": ["FAILED_GRADERS:contract_validator"],
            "policy_version": "governance_review_policy_v1",
            "hook": {"phase_id": "phase_01", "project_id": "autoloop-project", "prd_path": "/tmp/prd.md"},
        },
    )
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["governance-review", "--phase-id", "phase_01", "--no-resume"],
        )
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "Resolved by governance-review" in result.stdout
    assert (settings.hooks_dir / "phase_01_human_review_resolution.json").exists()


def test_diagnose_recovery_command_outputs_action(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    (tmp_path / "policies").mkdir(parents=True, exist_ok=True)
    settings.ensure_dirs()
    runner = CliRunner()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            [
                "diagnose-recovery",
                "--status",
                "failed",
                "--acceptance-status",
                "rejected",
                "--failure-type",
                "MISSING_DEV_RESULT",
                "--first-failure-stage",
                "dev_output_missing",
                "--failed-modules",
                "module_main",
            ],
        )
    finally:
        os.chdir(original_cwd)
    assert result.exit_code == 0
    assert "recommended_action" in result.stdout
    assert "replan_from_spec" in result.stdout


def test_apply_runner_health_delta_gate_marks_degraded_non_blocking_for_passed(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    summary_dir = settings.runtime_dir / "evidence" / "run_01" / "phase_01"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_file = summary_dir / "execution_summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "workflow_id": "run_01",
                "phase_id": "phase_01",
                "terminal_state": "ACCEPTED",
                "acceptance_status": "passed",
                "primary_failure_type": "",
                "secondary_failure_types": [],
                "recovery_action": "advance",
            }
        ),
        encoding="utf-8",
    )
    marker = _apply_runner_health_delta_gate(
        project_id="run_01",
        phase_id="phase_01",
        before={
            "state_db_fallback_count": 1,
            "session_degraded_count": 1,
            "execution_timeout_count": 1,
            "probe_failure_count": 1,
            "usage_limit_count": 1,
        },
        after={
            "state_db_fallback_count": 1,
            "session_degraded_count": 2,
            "execution_timeout_count": 1,
            "probe_failure_count": 1,
            "usage_limit_count": 1,
        },
    )
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert marker["runner_health_degraded_run"] is True
    assert payload["primary_failure_type"] == ""
    assert payload["runner_health_degraded_run"] is True
    assert "AGENT_RUNNER_SESSION_DEGRADED" in payload.get("non_blocking_signals", [])


def test_apply_runner_health_delta_gate_adds_secondary_for_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    summary_dir = settings.runtime_dir / "evidence" / "run_02" / "phase_01"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_file = summary_dir / "execution_summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "workflow_id": "run_02",
                "phase_id": "phase_01",
                "terminal_state": "REJECTED",
                "acceptance_status": "rejected",
                "primary_failure_type": "MISSING_REQUIRED_TEST",
                "secondary_failure_types": [],
                "recovery_action": "replan_from_spec",
            }
        ),
        encoding="utf-8",
    )
    marker = _apply_runner_health_delta_gate(
        project_id="run_02",
        phase_id="phase_01",
        before={
            "state_db_fallback_count": 0,
            "session_degraded_count": 0,
            "execution_timeout_count": 0,
            "probe_failure_count": 0,
            "usage_limit_count": 0,
        },
        after={
            "state_db_fallback_count": 1,
            "session_degraded_count": 0,
            "execution_timeout_count": 0,
            "probe_failure_count": 0,
            "usage_limit_count": 0,
        },
    )
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert marker["runner_health_degraded_run"] is True
    assert payload["primary_failure_type"] == "MISSING_REQUIRED_TEST"
    assert "STATE_DB_DEGRADED" in payload["secondary_failure_types"]


def test_apply_runner_health_delta_gate_timeout_only_does_not_mark_degraded(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    summary_dir = settings.runtime_dir / "evidence" / "run_03" / "phase_01"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_file = summary_dir / "execution_summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "workflow_id": "run_03",
                "phase_id": "phase_01",
                "terminal_state": "TIMEOUT",
                "acceptance_status": "rejected",
                "primary_failure_type": "GLOBAL_TIMEOUT",
                "secondary_failure_types": [],
                "recovery_action": "replan_from_spec",
            }
        ),
        encoding="utf-8",
    )
    marker = _apply_runner_health_delta_gate(
        project_id="run_03",
        phase_id="phase_01",
        before={
            "state_db_fallback_count": 0,
            "session_degraded_count": 0,
            "execution_timeout_count": 0,
            "probe_failure_count": 0,
            "usage_limit_count": 0,
        },
        after={
            "state_db_fallback_count": 0,
            "session_degraded_count": 0,
            "execution_timeout_count": 1,
            "probe_failure_count": 0,
            "usage_limit_count": 0,
        },
    )
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert marker["runner_health_timeout_delta_count"] == 1
    assert marker["runner_health_degraded_run"] is False
    assert payload["runner_health_degraded_run"] is False
    assert payload.get("runner_health_signals", []) == []


def test_apply_runner_health_delta_gate_probe_only_does_not_mark_degraded(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    summary_dir = settings.runtime_dir / "evidence" / "run_04" / "phase_01"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_file = summary_dir / "execution_summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "workflow_id": "run_04",
                "phase_id": "phase_01",
                "terminal_state": "ACCEPTED",
                "acceptance_status": "passed",
                "primary_failure_type": "",
                "secondary_failure_types": [],
                "recovery_action": "advance",
            }
        ),
        encoding="utf-8",
    )
    marker = _apply_runner_health_delta_gate(
        project_id="run_04",
        phase_id="phase_01",
        before={
            "state_db_fallback_count": 0,
            "session_degraded_count": 0,
            "execution_timeout_count": 0,
            "probe_failure_count": 0,
            "usage_limit_count": 0,
        },
        after={
            "state_db_fallback_count": 0,
            "session_degraded_count": 0,
            "execution_timeout_count": 0,
            "probe_failure_count": 2,
            "usage_limit_count": 0,
        },
    )
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert marker["runner_health_degraded_run"] is False
    assert payload["runner_health_degraded_run"] is False
    assert payload.get("runner_health_signals", []) == []
