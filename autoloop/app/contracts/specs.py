from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default="1.0")
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    workspace_id: str = Field(min_length=1)
    repo_root: str = Field(min_length=1)
    worktree_path: str = Field(min_length=1)
    base_sha: str = ""
    head_sha: str = ""
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    priority: str = Field(default="p1")
    risk_level: str = Field(default="medium")


class ChangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default="1.0")
    change_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    allowed_paths: list[str] = Field(default_factory=list, min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    required_symbols: list[str] = Field(default_factory=list)
    forbidden_symbols: list[str] = Field(default_factory=list)
    min_effective_diff_lines: int = Field(default=1, ge=0)
    must_update_tests: bool = Field(default=True)


class AcceptanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default="1.0")
    acceptance_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    required_tests: list[str] = Field(default_factory=list, min_length=1)
    required_graders: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    hidden_test_group: str = Field(default="core")
    rollback_on_failure: bool = Field(default=True)
    human_review_required: bool = Field(default=False)


def _module_result_artifact_path(*, phase_id: str, module_id: str) -> str:
    return f"app/{module_id}/artifacts/{phase_id}_result.json"


def build_contract_specs(
    *,
    project_id: str,
    phase_id: str,
    module_id: str,
    repo_root: str,
    worktree_path: str,
    base_sha: str = "",
    head_sha: str = "",
) -> tuple[TaskSpec, ChangeSpec, AcceptanceSpec]:
    task_id = f"task_{phase_id}_{module_id}"
    result_artifact_path = _module_result_artifact_path(phase_id=phase_id, module_id=module_id)
    task_spec = TaskSpec(
        task_id=task_id,
        project_id=project_id,
        phase_id=phase_id,
        module_id=module_id,
        requirement_ids=[f"req_{module_id}_core"],
        workspace_id=f"ws_{phase_id}_{module_id}",
        repo_root=repo_root,
        worktree_path=worktree_path,
        base_sha=base_sha,
        head_sha=head_sha,
        input_artifacts=[f"artifact_{phase_id}_prd"],
        output_artifacts=[result_artifact_path],
    )
    change_spec = ChangeSpec(
        change_id=f"change_{phase_id}_{module_id}",
        task_id=task_id,
        allowed_paths=[f"app/{module_id}/**", "app/**/*.py", "tests/**"],
        forbidden_paths=["runtime/**", "phases/**"],
        required_files=[],
        required_symbols=[],
    )
    acceptance_spec = AcceptanceSpec(
        acceptance_id=f"acceptance_{phase_id}_{module_id}",
        task_id=task_id,
        required_tests=["unit", "integration"],
        required_graders=["contract_validator"],
        required_artifacts=[result_artifact_path],
    )
    return task_spec, change_spec, acceptance_spec


def lint_contract_coherence(*, change_spec: ChangeSpec, acceptance_spec: AcceptanceSpec) -> list[str]:
    errors: list[str] = []
    required_tests = [str(item).strip().lower() for item in acceptance_spec.required_tests if str(item).strip()]
    allowed_paths = [str(item).strip().lower() for item in change_spec.allowed_paths if str(item).strip()]
    tests_path_allowed = any("test" in pattern for pattern in allowed_paths)
    if change_spec.must_update_tests and required_tests and not tests_path_allowed:
        errors.append(
            "must_update_tests=true but allowed_paths do not include any test path while required_tests is non-empty"
        )
    if required_tests and not change_spec.must_update_tests:
        errors.append(
            "required_tests is non-empty but must_update_tests=false"
        )
    return errors
