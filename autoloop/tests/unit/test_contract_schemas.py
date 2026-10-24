import json
from pathlib import Path

from app.contracts import (
    AcceptanceSpec,
    ChangeSpec,
    TaskSpec,
    build_contract_specs,
    lint_contract_coherence,
)


def test_contract_models_build_expected_specs():
    task_spec, change_spec, acceptance_spec = build_contract_specs(
        project_id="p1",
        phase_id="phase_01",
        module_id="module_main",
        repo_root="/repo",
        worktree_path="/repo/worktrees/module_main",
    )

    assert isinstance(task_spec, TaskSpec)
    assert isinstance(change_spec, ChangeSpec)
    assert isinstance(acceptance_spec, AcceptanceSpec)
    assert task_spec.task_id == "task_phase_01_module_main"
    assert "repo" in task_spec.repo_root
    assert "worktrees" in task_spec.worktree_path
    assert change_spec.task_id == task_spec.task_id
    assert acceptance_spec.task_id == task_spec.task_id
    assert len(change_spec.allowed_paths) > 0
    assert len(acceptance_spec.required_tests) > 0
    assert any("test" in pattern.lower() for pattern in change_spec.allowed_paths)


def test_contract_lint_detects_test_path_conflict():
    change_spec = ChangeSpec(
        change_id="c1",
        task_id="t1",
        allowed_paths=["app/main/**"],
        forbidden_paths=[],
        required_files=[],
        required_symbols=[],
        forbidden_symbols=[],
        must_update_tests=True,
    )
    acceptance_spec = AcceptanceSpec(
        acceptance_id="a1",
        task_id="t1",
        required_tests=["unit", "integration"],
        required_graders=["contract_validator"],
        required_artifacts=[],
    )
    errors = lint_contract_coherence(change_spec=change_spec, acceptance_spec=acceptance_spec)
    assert errors


def test_contract_schema_files_exist_and_require_core_fields():
    root = Path(__file__).resolve().parents[2]
    task_schema = json.loads(
        (root / "schemas" / "contracts" / "task_spec.schema.json").read_text(encoding="utf-8")
    )
    change_schema = json.loads(
        (root / "schemas" / "contracts" / "change_spec.schema.json").read_text(encoding="utf-8")
    )
    acceptance_schema = json.loads(
        (root / "schemas" / "contracts" / "acceptance_spec.schema.json").read_text(encoding="utf-8")
    )
    evidence_schema = json.loads(
        (root / "schemas" / "contracts" / "evidence_record.schema.json").read_text(encoding="utf-8")
    )

    assert "task_id" in task_schema["required"]
    assert "base_sha" in task_schema["required"]
    assert "head_sha" in task_schema["required"]
    assert "allowed_paths" in change_schema["required"]
    assert "required_tests" in acceptance_schema["required"]
    assert "acceptance_status" in evidence_schema["required"]
    assert "first_failure_stage" in evidence_schema["required"]
    assert "failure_type" in evidence_schema["required"]
    assert "primary_failure_type" in evidence_schema["required"]
    assert "secondary_failure_types" in evidence_schema["required"]
    assert "failure_signature" in evidence_schema["required"]
    assert "owner_agent" in evidence_schema["required"]
    assert "missing_artifacts" in evidence_schema["required"]
    assert "first_failure_at" in evidence_schema["required"]
    assert "first_failure_event_id" in evidence_schema["required"]
    assert "final_status_label" in evidence_schema["required"]
    assert "terminal_state" in evidence_schema["required"]
    assert "failure_events" in evidence_schema["required"]
    assert "event_log_file" in evidence_schema["required"]
