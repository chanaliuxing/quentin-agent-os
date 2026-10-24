import json

from app.config import settings
from app.models import AgentRole, default_contract_template
from app.temporal import activities as temporal_activities
from app.temporal.activities import _evaluate_acceptance_gate
from app.utils import ensure_phase_dirs, get_contract_file, get_result_file


def _write_acceptance_spec(phase_id: str, module_name: str, required_tests: list[str]) -> None:
    spec_file = get_contract_file(phase_id, module_name, "acceptance_spec")
    payload = {
        "contract_version": "1.0",
        "acceptance_id": f"acceptance_{phase_id}_{module_name}",
        "task_id": f"task_{phase_id}_{module_name}",
        "required_tests": required_tests,
        "required_graders": ["contract_validator"],
        "required_artifacts": [],
        "hidden_test_group": "core",
        "rollback_on_failure": True,
        "human_review_required": False,
    }
    spec_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_valid_results(phase_id: str, module_name: str) -> None:
    for role in (AgentRole.PLANNER, AgentRole.REVIEWER, AgentRole.DEV, AgentRole.QA):
        result_file = get_result_file(phase_id, role, module_name)
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(
            default_contract_template(role, module_name),
            encoding="utf-8",
        )


def test_acceptance_gate_rejects_missing_required_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["unit", "integration", "hidden"])
    _write_valid_results("phase_01", "module_main")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "unit", "status": "success"},
            {"gate": "integration", "status": "success"},
        ],
    )

    assert result["acceptance_status"] == "rejected"
    assert "hidden" in result["missing_required_tests"]
    assert result["failed_required_tests"] == []
    assert result["required_test_outcomes"]["hidden"] == "missing"


def test_acceptance_gate_rejects_when_contract_validator_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["unit", "integration"])
    _write_valid_results("phase_01", "module_main")

    dev_result_file = get_result_file("phase_01", AgentRole.DEV, "module_main")
    dev_result_file.write_text("not-json", encoding="utf-8")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "unit", "status": "success"},
            {"gate": "integration", "status": "success"},
        ],
    )

    assert result["acceptance_status"] == "rejected"
    assert result["grader_results"]["contract_validator"] == "fail"
    assert result["grader_details"]["contract_validator"]
    assert "INVALID_DEV_CONTRACT" in result["failure_types"]


def test_acceptance_gate_requires_successful_required_test_status(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["integration"])
    _write_valid_results("phase_01", "module_main")
    log_file = settings.logs_dir / "phase_01_integration.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("AssertionError: integration contract failed\n", encoding="utf-8")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "integration", "status": "failed", "log_file": str(log_file)},
            {"gate": "unit", "status": "success"},
        ],
    )

    assert result["acceptance_status"] == "rejected"
    assert result["missing_required_tests"] == []
    assert result["failed_required_tests"] == ["integration"]
    assert result["required_test_outcomes"]["integration"] == "failed"
    assert "REQUIRED_TEST_FAILED" in result["failure_types"]
    details = result["required_test_failure_details"]["integration"]
    assert details[0] == "required_test=integration"
    assert details[1] == "failure_type=REQUIRED_TEST_FAILED"
    assert details[2].startswith("location=")
    assert "AssertionError: integration contract failed" in details


def test_acceptance_gate_allows_regression_alias_for_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["integration"])
    _write_valid_results("phase_01", "module_main")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "regression", "status": "success"},
        ],
    )

    assert result["acceptance_status"] == "passed"
    assert result["missing_required_tests"] == []
    assert result["failed_required_tests"] == []


def test_acceptance_gate_alias_mapping_from_policy_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    policy_file = tmp_path / "policies" / "test_gate_policy.json"
    policy_file.parent.mkdir(parents=True, exist_ok=True)
    policy_file.write_text(
        json.dumps({"required_test_aliases": {"integration": ["static_scan"]}}),
        encoding="utf-8",
    )
    _write_acceptance_spec("phase_01", "module_main", ["integration"])
    _write_valid_results("phase_01", "module_main")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "static_scan", "status": "success"},
        ],
    )
    assert result["acceptance_status"] == "passed"


def test_acceptance_gate_marks_control_plane_when_required_test_detail_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["integration"])
    _write_valid_results("phase_01", "module_main")
    monkeypatch.setattr(
        temporal_activities,
        "_extract_required_test_failure_details",
        lambda **kwargs: [],
    )

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "integration", "status": "failed"},
        ],
    )

    assert result["acceptance_status"] == "rejected"
    assert result["failed_required_tests"] == ["integration"]
    assert result["missing_required_failure_details"] == ["integration"]
    assert "CONTROL_PLANE_MISSING_FAILURE_DETAIL" in result["failure_types"]
    assert "UNKNOWN_REQUIRED_TEST_FAILURE" in result["failure_types"]
    assert result["required_test_failure_details"]["integration"] == [
        "required_test=integration",
        "failure_type=UNKNOWN_REQUIRED_TEST_FAILURE",
        "location=unavailable",
        "reason=CONTROL_PLANE_MISSING_FAILURE_DETAIL",
    ]


def test_acceptance_gate_reports_binding_gap_when_required_gate_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["unit", "integration"])
    _write_valid_results("phase_01", "module_main")

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "unit", "status": "success"},
        ],
    )
    assert result["acceptance_status"] == "rejected"
    assert result["missing_required_tests"] == ["integration"]
    assert result["failed_required_tests"] == []
    assert result["required_test_outcomes"]["integration"] == "missing"
    assert "MISSING_TEST_BINDING" in result["failure_types"]


def test_acceptance_gate_rejects_when_state_db_fallback_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    monkeypatch.setattr(settings, "codex_fail_on_state_db_warning", True)
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["unit", "integration"])
    _write_valid_results("phase_01", "module_main")
    (settings.logs_dir / "phase_01_dev.log").write_text(
        "WARN codex_core::state_db: state db record_discrepancy: falling_back",
        encoding="utf-8",
    )

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "unit", "status": "success"},
            {"gate": "integration", "status": "success"},
        ],
    )
    assert result["acceptance_status"] == "rejected"
    assert result["grader_results"]["contract_validator"] == "fail"
    assert result["grader_details"]["contract_validator"][0]["error"] == "state_db_degraded"
    assert "STATE_DB_DEGRADED" in result["failure_types"]


def test_acceptance_gate_allows_state_db_warning_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    monkeypatch.setattr(settings, "codex_fail_on_state_db_warning", False)
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    _write_acceptance_spec("phase_01", "module_main", ["unit", "integration"])
    _write_valid_results("phase_01", "module_main")
    (settings.logs_dir / "phase_01_dev.log").write_text(
        "WARN codex_core::state_db: state db record_discrepancy: falling_back",
        encoding="utf-8",
    )

    result = _evaluate_acceptance_gate(
        phase_id="phase_01",
        modules=["module_main"],
        gate_results=[
            {"gate": "unit", "status": "success"},
            {"gate": "integration", "status": "success"},
        ],
    )
    assert result["acceptance_status"] == "passed"
