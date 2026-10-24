import re
import shlex
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from temporalio import activity

from app.config import settings
from app.models import AgentRole, AgentStatus, extract_json_payload, validate_output_contract
from app.runners import create_runner, AgentRunContext, AgentRunResult
from app.contracts import build_contract_specs, lint_contract_coherence
from app.workspace import resolve_workspace_identity, validate_claimed_paths
from app.utils import (
    ensure_phase_dirs,
    get_task_file,
    get_result_file,
    get_contract_file,
    write_task,
    run_subprocess_with_timeout,
)
from app.gitops import auto_resolve_conflicts_in_repo, detect_git_overlaps
from app.observability import log_event, trace_activity
from app.observability.metrics import MetricsCollector, MetricsTimer, classify_error
from app.review import build_review_task_patch
from app.evidence import EventRecord, EventStore
from app.temporal.action_state_contract import ActionStateContract


@activity.defn
@trace_activity("read_prd")
async def read_prd_activity(prd_path: str) -> str:
    log_event("read_prd", path=prd_path)

    prd_file = Path(prd_path)
    if not prd_file.exists():
        raise FileNotFoundError(f"PRD file not found: {prd_path}")

    return prd_file.read_text()


@activity.defn
@trace_activity("decompose_modules")
async def decompose_modules_activity(project_id: str, phase_id: str, prd_content: str) -> list[dict]:
    log_event("decompose_modules", project_id=project_id, phase_id=phase_id)
    modules: list[dict] = []
    for line in prd_content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## module"):
            name = stripped.lstrip("#").replace("Module", "", 1).strip()
            if name:
                modules.append({"name": _slug(name), "depends_on": []})

    if not modules:
        modules = [{"name": "module_main", "depends_on": []}]
    return modules


@activity.defn
@trace_activity("generate_phase_tasks")
async def generate_phase_tasks_activity(
    project_id: str, phase_id: str, prd_content: str, module_name: str | None = None
) -> dict:
    module_name = module_name or "module_main"
    ensure_phase_dirs(phase_id)
    log_event(
        "generate_phase_tasks",
        project_id=project_id,
        phase_id=phase_id,
        module_name=module_name,
    )

    workspace_identity = resolve_workspace_identity(settings.project_root)
    task_spec, change_spec, acceptance_spec = build_contract_specs(
        project_id=project_id,
        phase_id=phase_id,
        module_id=module_name,
        repo_root=workspace_identity.repo_root,
        worktree_path=workspace_identity.worktree_path,
        base_sha=workspace_identity.base_sha,
        head_sha=workspace_identity.head_sha,
    )
    contract_lint_errors = lint_contract_coherence(
        change_spec=change_spec,
        acceptance_spec=acceptance_spec,
    )
    if contract_lint_errors:
        error_text = "; ".join(contract_lint_errors)
        _append_runtime_event(
            project_id=project_id,
            phase_id=phase_id,
            stage="planner",
            actor="activity",
            event_type="CONTRACT_LINT_FAILED",
            failure_type="INVALID_TASK_CONTRACT",
            cause_class="business",
            payload={"module": module_name, "errors": contract_lint_errors},
        )
        raise ValueError(f"INVALID_TASK_CONTRACT:{module_name}:{error_text}")
    task_spec_file = get_contract_file(phase_id, module_name, "task_spec")
    change_spec_file = get_contract_file(phase_id, module_name, "change_spec")
    acceptance_spec_file = get_contract_file(phase_id, module_name, "acceptance_spec")
    task_spec_file.write_text(task_spec.model_dump_json(indent=2), encoding="utf-8")
    change_spec_file.write_text(change_spec.model_dump_json(indent=2), encoding="utf-8")
    acceptance_spec_file.write_text(acceptance_spec.model_dump_json(indent=2), encoding="utf-8")
    _append_runtime_event(
        project_id=project_id,
        phase_id=phase_id,
        stage="acceptance",
        actor="activity",
        event_type="ARTIFACT_DECLARED",
        cause_class="business",
        payload={
            "module": module_name,
            "required_artifacts": list(acceptance_spec.required_artifacts),
        },
        artifact_refs=[str(acceptance_spec_file)],
    )
    review_patch = build_review_task_patch(
        phase_id=phase_id,
        module_name=module_name,
    )
    review_patch_section = ""
    if review_patch:
        constraints_payload = review_patch.get("constraints", {})
        review_patch_section = f"""
## Human Review Patch
- Patch ID: {review_patch.get("patch_id", "")}
- Reviewer: {review_patch.get("reviewer", "")}
- Source: {review_patch.get("source", "")}
- Notes:
{review_patch.get("notes", "")}

## Enforced Repair Constraints (Machine-Readable)
```json
{json.dumps(constraints_payload, ensure_ascii=False, indent=2)}
```

You MUST apply this patch intent when producing output.
"""

    dev_task = f"""# Dev Task - {phase_id}

## PRD
{prd_content[:500]}...

## Tasks
Implement module: {module_name}

## Typed Contracts
- TaskSpec: {task_spec_file}
- ChangeSpec: {change_spec_file}
- AcceptanceSpec: {acceptance_spec_file}
- Schema IDs:
  - autoloop/schemas/contracts/task_spec.schema.json
  - autoloop/schemas/contracts/change_spec.schema.json
  - autoloop/schemas/contracts/acceptance_spec.schema.json

## Deliverables
Output strict JSON contract only.
{review_patch_section}
"""

    qa_task = f"""# QA Task - {phase_id}

## Tasks
Validate module: {module_name}
Run quality checks and verify functionality.

## Typed Contracts
- TaskSpec: {task_spec_file}
- ChangeSpec: {change_spec_file}
- AcceptanceSpec: {acceptance_spec_file}

## Deliverables
Output strict JSON contract only.
{review_patch_section}
"""

    planner_task = f"""# Planner Task - {phase_id}

## Module
{module_name}

## Context
{prd_content[:600]}...

## Your Tasks
1. Produce module implementation plan
2. Break down concrete tasks
3. Define acceptance criteria

## Typed Contracts
- TaskSpec: {task_spec_file}
- ChangeSpec: {change_spec_file}
- AcceptanceSpec: {acceptance_spec_file}

## Deliverables
Return strict JSON contract only.
{review_patch_section}
"""

    reviewer_task = f"""# Reviewer Task - {phase_id}

## Module
{module_name}

## Your Tasks
1. Review planner plan quality
2. Return approved or needs_revision
3. Provide concrete findings list
4. Provide machine-readable `finding_codes` (e.g. PATH_CONFLICT, MISSING_TEST_BINDING, CONTRACT_MISMATCH)

## Typed Contracts
- TaskSpec: {task_spec_file}
- ChangeSpec: {change_spec_file}
- AcceptanceSpec: {acceptance_spec_file}

## Deliverables
Return strict JSON contract only.
{review_patch_section}
"""

    dev_task_file = get_task_file(phase_id, AgentRole.DEV, module_name)
    qa_task_file = get_task_file(phase_id, AgentRole.QA, module_name)
    planner_task_file = get_task_file(phase_id, AgentRole.PLANNER, module_name)
    reviewer_task_file = get_task_file(phase_id, AgentRole.REVIEWER, module_name)

    with MetricsTimer() as dev_timer:
        write_task(dev_task_file, dev_task)
        from app.observability.metrics import task_generation_duration_seconds
        task_generation_duration_seconds.labels(
            phase=phase_id, agent_role="dev"
        ).observe(dev_timer.duration_seconds)

    with MetricsTimer() as qa_timer:
        write_task(qa_task_file, qa_task)
        task_generation_duration_seconds.labels(
            phase=phase_id, agent_role="qa"
        ).observe(qa_timer.duration_seconds)

    with MetricsTimer() as planner_timer:
        write_task(planner_task_file, planner_task)
        task_generation_duration_seconds.labels(
            phase=phase_id, agent_role="planner"
        ).observe(planner_timer.duration_seconds)

    with MetricsTimer() as reviewer_timer:
        write_task(reviewer_task_file, reviewer_task)
        task_generation_duration_seconds.labels(
            phase=phase_id, agent_role="reviewer"
        ).observe(reviewer_timer.duration_seconds)

    return {
        "module_name": module_name,
        "planner_task": str(planner_task_file),
        "reviewer_task": str(reviewer_task_file),
        "dev_task": str(dev_task_file),
        "qa_task": str(qa_task_file),
        "contract_files": {
            "task_spec": str(task_spec_file),
            "change_spec": str(change_spec_file),
            "acceptance_spec": str(acceptance_spec_file),
        },
        "review_patch_applied": bool(review_patch),
        "review_patch_source": str(review_patch.get("source", "")) if review_patch else "",
    }


@activity.defn
@trace_activity("run_agent")
async def run_agent_activity(
    project_id: str, phase_id: str, agent_name: str, module_name: str | None
) -> dict:
    log_event("run_agent", project_id=project_id, phase_id=phase_id, agent=agent_name)

    agent_role = AgentRole(agent_name)

    runner = create_runner()

    task_file = get_task_file(phase_id, agent_role, module_name)
    result_file = get_result_file(phase_id, agent_role, module_name)
    log_file = settings.logs_dir / f"{phase_id}_{agent_name}.log"
    working_dir = settings.project_root

    context = AgentRunContext(
        agent=agent_role,
        project_id=project_id,
        module_name=module_name,
        task_file=task_file,
        result_file=result_file,
        working_dir=working_dir,
        worktree_id=str(working_dir),
        log_file=log_file,
        phase_id=phase_id,
        timeout_seconds=max(1, settings.agent_timeout_seconds),
    )

    with MetricsTimer() as timer:
        attempt = 0
        last_error = ""
        last_failure_type = ""
        last_failure_detail: dict = {}
        last_runner_artifacts: dict = {}
        loop_started_at = datetime.now()
        max_retries = settings.agent_max_retries
        if settings.agent_runner_type == "codex":
            max_retries = min(max_retries, settings.codex_agent_max_retries)
        agent_budget_seconds = max(1, settings.agent_total_timeout_seconds)
        if agent_role == AgentRole.PLANNER:
            agent_budget_seconds = max(agent_budget_seconds, max(1, settings.planner_min_window_seconds))
        elif agent_role == AgentRole.REVIEWER:
            agent_budget_seconds = max(agent_budget_seconds, max(1, settings.reviewer_min_window_seconds))

        while attempt <= max_retries:
            elapsed = (datetime.now() - loop_started_at).total_seconds()
            if elapsed > agent_budget_seconds:
                last_error = f"agent_total_timeout_exceeded:{int(elapsed)}s"
                last_failure_type = "GLOBAL_TIMEOUT"
                _append_runtime_event(
                    project_id=project_id,
                    phase_id=phase_id,
                    stage=agent_name,
                    actor="activity",
                    event_type="STAGE_TIMEOUT",
                    failure_type="GLOBAL_TIMEOUT",
                    cause_class="execution",
                    payload={"module": module_name or "module_main", "elapsed_seconds": int(elapsed)},
                )
                break
            try:
                result = await runner.run(context)
                last_runner_artifacts = dict(result.artifacts or {})
                output_text = _get_output_text(result_file, result.stdout)

                contract_valid = False
                repair_attempts = 0
                contract_error = ""
                while repair_attempts <= settings.contract_repair_max_attempts:
                    try:
                        validate_output_contract(agent_role, output_text)
                        contract_valid = True
                        break
                    except Exception as exc:
                        contract_error = str(exc)
                        if repair_attempts == settings.contract_repair_max_attempts:
                            break
                        repair_attempts += 1
                        output_text = await _repair_contract_output(
                            runner=runner,
                            context=context,
                            module_name=module_name,
                            previous_output=output_text,
                            error_message=contract_error,
                            attempt=repair_attempts,
                        )

                status_value = result.status.value if contract_valid else AgentStatus.FAILED.value
                contract_payload = _safe_contract_parse(output_text)
                if contract_valid and _requires_constraint_ack(task_file):
                    if contract_payload.get("constraints_ack") is not True:
                        status_value = AgentStatus.FAILED.value
                        contract_error = "constraints_ack_missing_or_false"
                path_guard_error = ""
                if contract_valid and agent_role == AgentRole.DEV:
                    path_guard_result = _evaluate_dev_path_guard(
                        phase_id=phase_id,
                        module_name=module_name,
                        contract_payload=contract_payload,
                        repo_root=working_dir,
                    )
                    if not path_guard_result["ok"]:
                        status_value = AgentStatus.FAILED.value
                        path_guard_error = (
                            "claimed_file_changes outside allowed_paths: "
                            + ", ".join(path_guard_result["invalid_paths"])
                        )
                    ignored_paths = path_guard_result.get("ignored_paths", [])
                    if ignored_paths:
                        log_event(
                            "dev_path_guard_ignored_paths",
                            phase_id=phase_id,
                            module_name=module_name,
                            ignored_paths=ignored_paths,
                        )
                if status_value == AgentStatus.SUCCESS.value:
                    missing_required_artifacts = _missing_required_artifacts(
                        phase_id=phase_id,
                        module_name=module_name,
                        repo_root=working_dir,
                    )
                    if missing_required_artifacts and agent_role in {AgentRole.DEV, AgentRole.QA}:
                        failure_type = (
                            "MISSING_DEV_ARTIFACT"
                            if agent_role == AgentRole.DEV
                            else "MISSING_QA_ARTIFACT"
                        )
                        reason = (
                            f"missing_required_artifacts:{','.join(missing_required_artifacts)}"
                        )
                        _write_failure_contract_result(
                            result_file=result_file,
                            agent_role=agent_role,
                            module_name=module_name,
                            reason=reason,
                            failure_type=failure_type,
                        )
                        _append_runtime_event(
                            project_id=project_id,
                            phase_id=phase_id,
                            stage=agent_name,
                            actor="activity",
                            event_type="ARTIFACT_MISSING",
                            failure_type=failure_type,
                            cause_class="business",
                            payload={
                                "module": module_name or "module_main",
                                "missing_artifacts": missing_required_artifacts,
                            },
                            artifact_refs=missing_required_artifacts,
                        )
                        return {
                            "agent": agent_name,
                            "status": AgentStatus.FAILED.value,
                            "exit_code": result.exit_code,
                            "duration": result.duration_seconds,
                            "commit_sha": result.commit_sha,
                            "error": reason,
                            "contract_valid": False,
                            "repair_attempts": repair_attempts,
                            "agent_attempts": attempt + 1,
                            "contract": {},
                            "failure_type": failure_type,
                            "failure_severity": "soft_fail",
                            "missing_artifacts": missing_required_artifacts,
                        }
                    if not _persist_contract_output(result_file, output_text):
                        last_error = "result_file_missing_or_empty"
                        attempt += 1
                        if attempt > max_retries:
                            break
                        continue
                    MetricsCollector.record_agent_execution(
                        agent_role=agent_name,
                        runner_type=settings.agent_runner_type,
                        status=status_value,
                        duration_seconds=timer.duration_seconds,
                    )
                    return {
                        "agent": agent_name,
                        "status": status_value,
                        "exit_code": result.exit_code,
                        "duration": result.duration_seconds,
                        "commit_sha": result.commit_sha,
                        "error": result.error_message or contract_error,
                        "contract_valid": contract_valid,
                        "repair_attempts": repair_attempts,
                        "agent_attempts": attempt + 1,
                        "contract": contract_payload,
                        "failure_type": "",
                        "failure_severity": "",
                        "missing_artifacts": [],
                        "runner_artifacts": dict(result.artifacts or {}),
                    }

                last_error = result.error_message or contract_error or path_guard_error or "unknown"
                failure_type = _infer_failure_type(
                    agent_role=agent_role,
                    error_message=last_error,
                    result=result,
                    output_text=output_text,
                    contract_valid=contract_valid,
                    contract_error=contract_error,
                )
                _write_failure_contract_result(
                    result_file=result_file,
                    agent_role=agent_role,
                    module_name=module_name,
                    reason=last_error,
                    failure_type=failure_type,
                )
                _append_runtime_event(
                    project_id=project_id,
                    phase_id=phase_id,
                    stage=agent_name,
                    actor="activity",
                    event_type=_event_type_from_failure_type(failure_type),
                    failure_type=failure_type,
                    cause_class=_cause_class_from_failure_type(failure_type),
                    payload={
                        "module": module_name or "module_main",
                        "reason": last_error[:300],
                        **(
                            {"subprocess_detail": _extract_subprocess_failure_detail(result=result, error_message=last_error)}
                            if failure_type == "AGENT_SUBPROCESS_NONZERO_EXIT"
                            else {}
                        ),
                    },
                )
                last_failure_type = failure_type
                last_failure_detail = (
                    _extract_subprocess_failure_detail(result=result, error_message=last_error)
                    if failure_type == "AGENT_SUBPROCESS_NONZERO_EXIT"
                    else {}
                )
                if _is_non_retryable_error(last_error):
                    break
                attempt += 1
                if attempt > max_retries:
                    break
            except Exception as exc:
                last_error = str(exc)
                failure_type = _infer_failure_type(
                    agent_role=agent_role,
                    error_message=last_error,
                )
                _write_failure_contract_result(
                    result_file=result_file,
                    agent_role=agent_role,
                    module_name=module_name,
                    reason=last_error,
                    failure_type=failure_type,
                )
                _append_runtime_event(
                    project_id=project_id,
                    phase_id=phase_id,
                    stage=agent_name,
                    actor="activity",
                    event_type=_event_type_from_failure_type(failure_type),
                    failure_type=failure_type,
                    cause_class=_cause_class_from_failure_type(failure_type),
                    payload={"module": module_name or "module_main", "reason": last_error[:300]},
                )
                last_failure_type = failure_type
                last_failure_detail = {}
                if _is_non_retryable_error(last_error):
                    break
                attempt += 1
                if attempt > max_retries:
                    error_type = classify_error(exc)
                    MetricsCollector.increment_errors(agent_name, error_type)
                    break

        MetricsCollector.record_agent_execution(
            agent_role=agent_name,
            runner_type=settings.agent_runner_type,
            status="failed",
            duration_seconds=timer.duration_seconds,
        )
        MetricsCollector.increment_errors(agent_name, classify_error(Exception(last_error or "unknown")))
        return {
            "agent": agent_name,
            "status": AgentStatus.FAILED.value,
            "exit_code": -1,
            "duration": timer.duration_seconds,
            "commit_sha": None,
            "error": last_error,
            "contract_valid": False,
            "repair_attempts": settings.contract_repair_max_attempts,
            "agent_attempts": attempt,
            "contract": {},
            "failure_type": last_failure_type
            or _infer_failure_type(agent_role=agent_role, error_message=last_error),
            "failure_severity": _infer_failure_severity(last_error),
            "missing_artifacts": _extract_missing_artifacts(last_error),
            "runner_artifacts": last_runner_artifacts,
            "failure_detail": last_failure_detail,
        }


@activity.defn
@trace_activity("collect_results")
async def collect_results_activity(project_id: str, phase_id: str, modules: list[str] | None = None) -> dict:
    log_event("collect_results", project_id=project_id, phase_id=phase_id)

    from app.observability.metrics import result_collection_duration_seconds

    modules = modules or ["module_main"]
    results = {}
    for module_name in modules:
        module_results = {}
        for agent in [AgentRole.PLANNER, AgentRole.REVIEWER, AgentRole.DEV, AgentRole.QA]:
            with MetricsTimer() as timer:
                result_file = get_result_file(phase_id, agent, module_name)
                if result_file.exists():
                    module_results[agent.value] = result_file.read_text()
                else:
                    module_results[agent.value] = "No result file found"

                result_collection_duration_seconds.labels(
                    phase=phase_id, agent_role=agent.value
                ).observe(timer.duration_seconds)
        results[module_name] = module_results

    return results


@activity.defn
@trace_activity("run_module_pipeline")
async def run_module_pipeline_activity(
    project_id: str, phase_id: str, module_name: str
) -> dict:
    previous_results = _snapshot_existing_results(phase_id=phase_id, module_name=module_name)
    planner_loops = 0
    planner_status = "failed"
    reviewer_status = "failed"
    reviewer_verdict = "needs_revision"
    planner_result = {}
    reviewer_result = {}
    reviewer_history: list[dict] = []
    state_contracts: list[dict] = []
    last_reviewer_signature = ""
    stagnation_rounds = 0
    while planner_loops <= settings.max_planner_reviewer_loops:
        round_index = planner_loops + 1
        planner_contract_state = _build_planner_handoff_contract(
            phase_id=phase_id,
            module_name=module_name,
            round_index=round_index,
        )
        planner_result = await run_agent_activity(
            project_id=project_id,
            phase_id=phase_id,
            agent_name=AgentRole.PLANNER.value,
            module_name=module_name,
        )
        planner_status = planner_result.get("status", "failed")
        _ensure_materialized_result_file(
            phase_id=phase_id,
            agent_role=AgentRole.PLANNER,
            module_name=module_name,
            agent_result=planner_result,
        )
        _snapshot_result_version(
            phase_id=phase_id,
            agent_role=AgentRole.PLANNER,
            module_name=module_name,
            round_index=round_index,
            status=str(planner_status),
        )
        planner_handoff_verified, planner_handoff_observed = _verify_planner_handoff_contract(planner_contract_state)
        planner_contract_state.observed_state = planner_handoff_observed
        planner_contract_state.verified = planner_handoff_verified
        if not planner_handoff_verified and planner_status == AgentStatus.SUCCESS.value:
            planner_status = AgentStatus.FAILED.value
            planner_result = dict(planner_result)
            planner_result["status"] = AgentStatus.FAILED.value
            planner_result["error"] = "planner_handoff_state_mismatch"
            planner_result["failure_type"] = "PLANNER_HANDOFF_STATE_MISMATCH"
            _rollback_planner_handoff_contract(
                phase_id=phase_id,
                module_name=module_name,
                previous_results=previous_results,
            )
        state_contracts.append(planner_contract_state.model_dump(mode="json"))
        if planner_status != AgentStatus.SUCCESS.value:
            break

        reviewer_result = await run_agent_activity(
            project_id=project_id,
            phase_id=phase_id,
            agent_name=AgentRole.REVIEWER.value,
            module_name=module_name,
        )
        reviewer_status = reviewer_result.get("status", "failed")
        _ensure_materialized_result_file(
            phase_id=phase_id,
            agent_role=AgentRole.REVIEWER,
            module_name=module_name,
            agent_result=reviewer_result,
        )
        _snapshot_result_version(
            phase_id=phase_id,
            agent_role=AgentRole.REVIEWER,
            module_name=module_name,
            round_index=round_index,
            status=str(reviewer_status),
        )
        reviewer_verdict = str(reviewer_result.get("contract", {}).get("verdict", "approved"))
        findings = reviewer_result.get("contract", {}).get("findings", [])
        findings_signature = json.dumps(findings, ensure_ascii=False, sort_keys=True)
        reviewer_history.append(
            {
                "status": reviewer_status,
                "verdict": reviewer_verdict,
                "findings_signature": findings_signature,
            }
        )
        if reviewer_status == AgentStatus.SUCCESS.value and reviewer_verdict == "approved":
            break
        if reviewer_status == AgentStatus.SUCCESS.value and reviewer_verdict != "approved":
            if findings_signature == last_reviewer_signature:
                stagnation_rounds += 1
            else:
                stagnation_rounds = 0
            last_reviewer_signature = findings_signature
            if stagnation_rounds >= 1:
                break
        planner_loops += 1

    reviewer_gate_passed = (
        planner_status == AgentStatus.SUCCESS.value
        and reviewer_status == AgentStatus.SUCCESS.value
        and reviewer_verdict == "approved"
    )
    if planner_status != AgentStatus.SUCCESS.value:
        _restore_previous_result_if_missing(
            phase_id=phase_id,
            agent_role=AgentRole.PLANNER,
            module_name=module_name,
            previous_results=previous_results,
        )
        _write_failure_contract_result(
            result_file=get_result_file(phase_id, AgentRole.REVIEWER, module_name),
            agent_role=AgentRole.REVIEWER,
            module_name=module_name,
            reason="blocked_by_planner",
            failure_type="RUNNER_BLOCKED",
        )
    dev_result = {
        "agent": AgentRole.DEV.value,
        "status": AgentStatus.FAILED.value,
        "error": "blocked_by_reviewer",
    }
    qa_result = {"status": AgentStatus.FAILED.value}
    if not reviewer_gate_passed:
        _write_failure_contract_result(
            result_file=get_result_file(phase_id, AgentRole.DEV, module_name),
            agent_role=AgentRole.DEV,
            module_name=module_name,
            reason="blocked_by_reviewer",
            failure_type="RUNNER_BLOCKED",
        )
        _write_failure_contract_result(
            result_file=get_result_file(phase_id, AgentRole.QA, module_name),
            agent_role=AgentRole.QA,
            module_name=module_name,
            reason="blocked_by_reviewer",
            failure_type="RUNNER_BLOCKED",
        )
    if reviewer_gate_passed:
        dev_contract_state = _build_role_handoff_contract(
            phase_id=phase_id,
            module_name=module_name,
            round_index=planner_loops + 1,
            agent_role=AgentRole.DEV,
            handoff_name="dev_handoff",
        )
        dev_result = await run_agent_activity(
            project_id=project_id,
            phase_id=phase_id,
            agent_name=AgentRole.DEV.value,
            module_name=module_name,
        )
        _ensure_materialized_result_file(
            phase_id=phase_id,
            agent_role=AgentRole.DEV,
            module_name=module_name,
            agent_result=dev_result,
        )
        _snapshot_result_version(
            phase_id=phase_id,
            agent_role=AgentRole.DEV,
            module_name=module_name,
            round_index=planner_loops + 1,
            status=str(dev_result.get("status", "failed")),
        )
        dev_handoff_verified, dev_handoff_observed = _verify_role_handoff_contract(
            contract=dev_contract_state,
            agent_role=AgentRole.DEV,
        )
        dev_contract_state.observed_state = dev_handoff_observed
        dev_contract_state.verified = dev_handoff_verified
        if not dev_handoff_verified and dev_result.get("status") == AgentStatus.SUCCESS.value:
            dev_result = dict(dev_result)
            dev_result["status"] = AgentStatus.FAILED.value
            dev_result["error"] = "dev_handoff_state_mismatch"
            dev_result["failure_type"] = "DEV_HANDOFF_STATE_MISMATCH"
            _rollback_role_handoff_contract(
                phase_id=phase_id,
                module_name=module_name,
                previous_results=previous_results,
                agent_role=AgentRole.DEV,
            )
        state_contracts.append(dev_contract_state.model_dump(mode="json"))
    if reviewer_gate_passed and dev_result.get("status") == AgentStatus.SUCCESS.value:
        qa_contract_state = _build_role_handoff_contract(
            phase_id=phase_id,
            module_name=module_name,
            round_index=planner_loops + 1,
            agent_role=AgentRole.QA,
            handoff_name="qa_handoff",
        )
        qa_result = await run_agent_activity(
            project_id=project_id,
            phase_id=phase_id,
            agent_name=AgentRole.QA.value,
            module_name=module_name,
        )
        _ensure_materialized_result_file(
            phase_id=phase_id,
            agent_role=AgentRole.QA,
            module_name=module_name,
            agent_result=qa_result,
        )
        _snapshot_result_version(
            phase_id=phase_id,
            agent_role=AgentRole.QA,
            module_name=module_name,
            round_index=planner_loops + 1,
            status=str(qa_result.get("status", "failed")),
        )
        qa_handoff_verified, qa_handoff_observed = _verify_role_handoff_contract(
            contract=qa_contract_state,
            agent_role=AgentRole.QA,
        )
        qa_contract_state.observed_state = qa_handoff_observed
        qa_contract_state.verified = qa_handoff_verified
        if not qa_handoff_verified and qa_result.get("status") == AgentStatus.SUCCESS.value:
            qa_result = dict(qa_result)
            qa_result["status"] = AgentStatus.FAILED.value
            qa_result["error"] = "qa_handoff_state_mismatch"
            qa_result["failure_type"] = "QA_HANDOFF_STATE_MISMATCH"
            _rollback_role_handoff_contract(
                phase_id=phase_id,
                module_name=module_name,
                previous_results=previous_results,
                agent_role=AgentRole.QA,
            )
        state_contracts.append(qa_contract_state.model_dump(mode="json"))
    if reviewer_gate_passed and dev_result.get("status") != AgentStatus.SUCCESS.value:
        _write_failure_contract_result(
            result_file=get_result_file(phase_id, AgentRole.QA, module_name),
            agent_role=AgentRole.QA,
            module_name=module_name,
            reason="blocked_by_dev_failure",
            failure_type="RUNNER_BLOCKED",
        )

    module_success = (
        planner_status == AgentStatus.SUCCESS.value
        and reviewer_status == AgentStatus.SUCCESS.value
        and reviewer_verdict == "approved"
        and dev_result.get("status") == AgentStatus.SUCCESS.value
        and qa_result.get("status") == AgentStatus.SUCCESS.value
    )
    return {
        "module_name": module_name,
        "status": "success" if module_success else "failed",
        "planner_result": planner_result,
        "reviewer_result": reviewer_result,
        "dev_result": dev_result,
        "qa_result": qa_result,
        "planner_loops": planner_loops,
        "reviewer_history": reviewer_history,
        "review_stagnated": stagnation_rounds >= 1,
        "state_contracts": state_contracts,
    }


def _build_planner_handoff_contract(*, phase_id: str, module_name: str, round_index: int) -> ActionStateContract:
    return _build_role_handoff_contract(
        phase_id=phase_id,
        module_name=module_name,
        round_index=round_index,
        agent_role=AgentRole.PLANNER,
        handoff_name="planner_handoff",
    )


def _build_role_handoff_contract(
    *,
    phase_id: str,
    module_name: str,
    round_index: int,
    agent_role: AgentRole,
    handoff_name: str,
) -> ActionStateContract:
    result_file = get_result_file(phase_id, AgentRole.PLANNER, module_name)
    if agent_role != AgentRole.PLANNER:
        result_file = get_result_file(phase_id, agent_role, module_name)
    history_dir = result_file.parent / "history"
    pre_state = {
        "result_exists": result_file.exists() and bool(result_file.read_text(encoding="utf-8").strip())
        if result_file.exists()
        else False,
        "result_hash": _safe_file_hash(result_file),
        "history_count": _history_count(history_dir),
    }
    return ActionStateContract(
        action_id=f"{phase_id}:{module_name}:{handoff_name}:round_{round_index:02d}",
        pre_state=pre_state,
        expected_state_delta={
            "result_materialized": True,
            "history_count_incremented": True,
            "contract_valid": True,
        },
        verify_rule="result_exists && history_count_increased && contract_valid",
        rollback_hook=f"restore_previous_{agent_role.value}_result_if_missing_or_invalid",
    )


def _verify_planner_handoff_contract(contract: ActionStateContract) -> tuple[bool, dict]:
    return _verify_role_handoff_contract(contract=contract, agent_role=AgentRole.PLANNER)


def _verify_role_handoff_contract(*, contract: ActionStateContract, agent_role: AgentRole) -> tuple[bool, dict]:
    action_id = contract.action_id
    parts = action_id.split(":")
    phase_id = parts[0]
    module_name = parts[1]
    result_file = get_result_file(phase_id, agent_role, module_name)
    history_dir = result_file.parent / "history"
    observed_state = {
        "result_exists": result_file.exists() and bool(result_file.read_text(encoding="utf-8").strip())
        if result_file.exists()
        else False,
        "result_hash": _safe_file_hash(result_file),
        "history_count": _history_count(history_dir),
        "contract_valid": False,
    }
    if result_file.exists():
        payload = result_file.read_text(encoding="utf-8").strip()
        if payload:
            try:
                validate_output_contract(agent_role, payload)
                observed_state["contract_valid"] = True
            except Exception:
                observed_state["contract_valid"] = False
    history_incremented = int(observed_state["history_count"]) > int(
        contract.pre_state.get("history_count", 0)
    )
    verified = (
        bool(observed_state["result_exists"])
        and bool(observed_state["contract_valid"])
        and history_incremented
    )
    return verified, observed_state


def _rollback_planner_handoff_contract(
    *,
    phase_id: str,
    module_name: str,
    previous_results: dict[AgentRole, str],
) -> None:
    _rollback_role_handoff_contract(
        phase_id=phase_id,
        module_name=module_name,
        previous_results=previous_results,
        agent_role=AgentRole.PLANNER,
    )


def _rollback_role_handoff_contract(
    *,
    phase_id: str,
    module_name: str,
    previous_results: dict[AgentRole, str],
    agent_role: AgentRole,
) -> None:
    result_file = get_result_file(phase_id, agent_role, module_name)
    if result_file.exists():
        try:
            text = result_file.read_text(encoding="utf-8").strip()
            if text:
                validate_output_contract(agent_role, text)
                return
        except Exception:
            result_file.unlink(missing_ok=True)
    _restore_previous_result_if_missing(
        phase_id=phase_id,
        agent_role=agent_role,
        module_name=module_name,
        previous_results=previous_results,
    )


def _history_count(history_dir: Path) -> int:
    if not history_dir.exists():
        return 0
    return len([item for item in history_dir.glob("*.md") if item.is_file()])


def _safe_file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_materialized_result_file(
    *,
    phase_id: str,
    agent_role: AgentRole,
    module_name: str,
    agent_result: dict,
) -> None:
    if str(agent_result.get("status", "")).strip().lower() != AgentStatus.SUCCESS.value:
        return
    result_file = get_result_file(phase_id, agent_role, module_name)
    if result_file.exists() and result_file.read_text(encoding="utf-8").strip():
        return
    contract_payload = agent_result.get("contract", {})
    if not isinstance(contract_payload, dict) or not contract_payload:
        return
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(contract_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot_result_version(
    *,
    phase_id: str,
    agent_role: AgentRole,
    module_name: str,
    round_index: int,
    status: str,
) -> None:
    result_file = get_result_file(phase_id, agent_role, module_name)
    if not result_file.exists():
        return
    text = result_file.read_text(encoding="utf-8").strip()
    if not text:
        return
    history_dir = result_file.parent / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    safe_status = re.sub(r"[^a-z0-9_]+", "_", str(status).strip().lower() or "unknown")
    history_file = history_dir / (
        f"{module_name}_{agent_role.value}.round_{round_index:02d}.{safe_status}.{timestamp}.md"
    )
    history_file.write_text(text + "\n", encoding="utf-8")


def _snapshot_existing_results(*, phase_id: str, module_name: str) -> dict[AgentRole, str]:
    snapshot: dict[AgentRole, str] = {}
    for role in (AgentRole.PLANNER, AgentRole.REVIEWER, AgentRole.DEV, AgentRole.QA):
        result_file = get_result_file(phase_id, role, module_name)
        if not result_file.exists():
            continue
        text = result_file.read_text(encoding="utf-8").strip()
        if text:
            snapshot[role] = text
    return snapshot


def _restore_previous_result_if_missing(
    *,
    phase_id: str,
    agent_role: AgentRole,
    module_name: str,
    previous_results: dict[AgentRole, str],
) -> None:
    result_file = get_result_file(phase_id, agent_role, module_name)
    if result_file.exists() and result_file.read_text(encoding="utf-8").strip():
        return
    previous_text = previous_results.get(agent_role, "").strip()
    if not previous_text:
        return
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(previous_text, encoding="utf-8")


@activity.defn
@trace_activity("git_overlap_report")
async def git_overlap_report_activity(project_id: str, phase_id: str) -> dict:
    log_event("git_overlap_report", project_id=project_id, phase_id=phase_id)

    overlaps = detect_git_overlaps(
        repo_path=settings.project_root,
        phase_id=phase_id,
        agent_commits={
            AgentRole.DEV: ["mock_dev_commit"],
            AgentRole.QA: ["mock_qa_commit"],
        },
    )

    for overlap in overlaps:
        risk_level = overlap.risk_level if hasattr(overlap, "risk_level") else "medium"
        MetricsCollector.increment_conflicts(phase_id, risk_level, count=1)

    resolved_files: list[str] = []
    if settings.git_auto_resolve_conflicts and overlaps:
        resolved_files = auto_resolve_conflicts_in_repo(settings.project_root, strategy="ours")

    return {
        "overlaps_count": len(overlaps),
        "overlaps": [o.model_dump() for o in overlaps],
        "resolved_files": resolved_files,
    }


@activity.defn
@trace_activity("integration_test")
async def integration_test_activity(
    project_id: str, phase_id: str, modules: list[str] | None = None
) -> dict:
    log_event("integration_test", project_id=project_id, phase_id=phase_id)

    with MetricsTimer() as timer:
        test_status = "success"
        gates = [
            ("compile", settings.gate_compile_command, True),
            ("unit", settings.gate_unit_test_command, True),
            ("integration", settings.gate_integration_test_command, True),
            ("regression", settings.gate_regression_test_command, True),
            ("static_scan", settings.gate_static_scan_command, True),
            ("benchmark", settings.gate_benchmark_command, False),
        ]
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        gate_results: list[dict] = []
        try:
            for gate_name, command, hard_fail in gates:
                if not command.strip():
                    continue
                tests_run += 1
                gate_result = await _run_quality_gate(
                    phase_id=phase_id,
                    gate_name=gate_name,
                    command=command,
                )
                gate_results.append(gate_result)
                if gate_result["status"] == "success":
                    tests_passed += 1
                else:
                    tests_failed += 1
                    if hard_fail:
                        test_status = "failed"

            acceptance_eval = _evaluate_acceptance_gate(
                phase_id=phase_id,
                gate_results=gate_results,
                modules=modules or ["module_main"],
            )
            result = {
                "status": test_status,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "gate_results": gate_results,
                "orchestration_status": "completed",
                "execution_status": "tests_passed" if test_status == "success" else "tests_failed",
                "acceptance_status": acceptance_eval["acceptance_status"],
                "missing_required_tests": acceptance_eval["missing_required_tests"],
                "failed_required_tests": acceptance_eval["failed_required_tests"],
                "required_test_outcomes": acceptance_eval["required_test_outcomes"],
                "required_test_failure_details": acceptance_eval["required_test_failure_details"],
                "grader_results": acceptance_eval["grader_results"],
                "grader_details": acceptance_eval["grader_details"],
                "failure_types": acceptance_eval["failure_types"],
            }
            return result
        except Exception as exc:
            test_status = "failed"
            raise
        finally:
            from app.observability.metrics import integration_test_duration_seconds
            integration_test_duration_seconds.labels(
                phase=phase_id, status=test_status
            ).observe(timer.duration_seconds)


@activity.defn
@trace_activity("write_phase_report")
async def write_phase_report_activity(
    project_id: str, phase_id: str, results: dict, overlap_report: dict, test_results: dict
) -> str:
    log_event("write_phase_report", project_id=project_id, phase_id=phase_id)

    module_sections = []
    for module_name, module_results in results.items():
        module_sections.append(
            f"""### Module: {module_name}

#### Dev
{module_results.get('dev', 'N/A')}

#### QA
{module_results.get('qa', 'N/A')}
"""
        )

    test_status = test_results.get("status", "unknown")
    orchestration_status = str(test_results.get("orchestration_status", "completed"))
    execution_status = str(
        test_results.get(
            "execution_status",
            "tests_passed" if test_status == "success" else "tests_failed",
        )
    )
    missing_results = any(
        "No result file found" in str(module_results.get(agent, ""))
        for module_results in results.values()
        for agent in ("planner", "reviewer", "dev", "qa")
    )
    acceptance_status = str(
        test_results.get(
            "acceptance_status",
            "passed" if test_status == "success" and not missing_results else "rejected",
        )
    )
    phase_success = acceptance_status == "passed"
    missing_required_tests = [
        str(item) for item in test_results.get("missing_required_tests", []) if str(item).strip()
    ]
    failed_required_tests = [
        str(item) for item in test_results.get("failed_required_tests", []) if str(item).strip()
    ]
    required_test_failure_details = {
        str(key): [str(item) for item in value if str(item).strip()]
        for key, value in test_results.get("required_test_failure_details", {}).items()
        if isinstance(value, list)
    }
    required_tests_lines: list[str] = []
    if missing_required_tests:
        required_tests_lines.append(f"Missing required tests: {', '.join(sorted(missing_required_tests))}")
    if failed_required_tests:
        required_tests_lines.append(f"Failed required tests: {', '.join(sorted(failed_required_tests))}")
    for test_name, details in sorted(required_test_failure_details.items()):
        if not details:
            continue
        required_tests_lines.append(f"{test_name} failure summary:")
        required_tests_lines.extend([f"- {line}" for line in details[:5]])
    required_tests_section = (
        "\n".join(required_tests_lines)
        if required_tests_lines
        else "No required test gaps detected."
    )
    summary_line = (
        f"Phase {phase_id} completed successfully."
        if phase_success
        else (
            f"Phase {phase_id} failed acceptance gate "
            f"(acceptance_status={acceptance_status}, test_status={test_status}, missing_results={missing_results})."
        )
    )

    report_content = f"""# Phase Report: {phase_id}

## Project: {project_id}

## Agent Results

{chr(10).join(module_sections)}

## Git Overlap Analysis
Overlaps found: {overlap_report.get('overlaps_count', 0)}

## Integration Tests
Status: {test_results.get('status', 'N/A')}
Tests run: {test_results.get('tests_run', 0)}
Passed: {test_results.get('tests_passed', 0)}
Failed: {test_results.get('tests_failed', 0)}

## Required Test Diagnostics
{required_tests_section}

## Semantic Status
Orchestration: {orchestration_status}
Execution: {execution_status}
Acceptance: {acceptance_status}

## Summary
{summary_line}
"""

    report_file = settings.phases_dir / phase_id / "phase_report.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report_content)

    return str(report_file)


def _slug(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    slug = "".join(out).strip("_")
    return slug or "module_main"


def _reset_module_result_files(*, phase_id: str, module_name: str) -> None:
    for role in (AgentRole.PLANNER, AgentRole.REVIEWER, AgentRole.DEV, AgentRole.QA):
        result_file = get_result_file(phase_id, role, module_name)
        if result_file.exists():
            result_file.unlink()


def _get_output_text(result_file: Path, stdout_text: str) -> str:
    if result_file.exists():
        text = result_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return (stdout_text or "").strip()


def _requires_constraint_ack(task_file: Path) -> bool:
    if not task_file.exists():
        return False
    try:
        text = task_file.read_text(encoding="utf-8")
    except Exception:
        return False
    return "Enforced Repair Constraints (Machine-Readable)" in text


def _persist_contract_output(result_file: Path, output_text: str) -> bool:
    text = (output_text or "").strip()
    if not text:
        return False
    if result_file.exists() and result_file.read_text(encoding="utf-8").strip():
        return True
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(text, encoding="utf-8")
    return True


async def _repair_contract_output(
    *,
    runner,
    context: AgentRunContext,
    module_name: str | None,
    previous_output: str,
    error_message: str,
    attempt: int,
) -> str:
    repair_task = context.task_file.parent / f"{context.task_file.stem}_repair_{attempt}.md"
    repair_prompt = (
        context.task_file.read_text(encoding="utf-8")
        + "\n\nPrevious output was invalid JSON contract.\n"
        + f"Validation error: {error_message}\n"
        + "Return only strict JSON matching required contract fields.\n"
        + f"Previous output:\n{previous_output[:2000]}\n"
    )
    repair_task.write_text(repair_prompt, encoding="utf-8")
    repair_context = context.model_copy(update={"task_file": repair_task})
    repair_result = await runner.run(repair_context)
    return _get_output_text(context.result_file, repair_result.stdout)


async def _run_quality_gate(*, phase_id: str, gate_name: str, command: str) -> dict:
    log_file = settings.logs_dir / f"{phase_id}_{gate_name}.log"
    cmd = shlex.split(command)
    with MetricsTimer() as timer:
        result = await run_subprocess_with_timeout(
            cmd=cmd,
            cwd=str(settings.project_root),
            timeout=settings.agent_timeout_seconds,
            log_file=log_file,
        )
    status = "success" if result["returncode"] == 0 else "failed"
    output = f"{result['stdout']}\n{result['stderr']}"
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    return {
        "gate": gate_name,
        "status": status,
        "duration_seconds": timer.duration_seconds,
        "exit_code": result["returncode"],
        "passed": int(passed_match.group(1)) if passed_match else 0,
        "failed": int(failed_match.group(1)) if failed_match else 0,
        "log_file": str(log_file),
    }


def _safe_contract_parse(text: str) -> dict:
    try:
        return extract_json_payload(text)
    except Exception:
        return {}


def _evaluate_acceptance_gate(
    *,
    phase_id: str,
    gate_results: list[dict],
    modules: list[str],
) -> dict:
    required_tests: set[str] = set()
    required_graders: set[str] = set()
    for module_name in modules:
        spec_file = get_contract_file(phase_id, module_name, "acceptance_spec")
        if not spec_file.exists():
            continue
        try:
            spec_payload = json.loads(spec_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        required_tests.update(str(item) for item in spec_payload.get("required_tests", []))
        required_graders.update(str(item) for item in spec_payload.get("required_graders", []))

    gate_status_map = {
        str(item.get("gate", "")): str(item.get("status", "failed")) for item in gate_results
    }
    gate_result_map = {
        str(item.get("gate", "")): dict(item)
        for item in gate_results
        if str(item.get("gate", "")).strip()
    }
    required_test_outcomes = _evaluate_required_test_outcomes(
        required_tests=required_tests,
        gate_status_map=gate_status_map,
    )
    missing_required_tests = sorted(
        test_name for test_name, outcome in required_test_outcomes.items() if outcome == "missing"
    )
    failed_required_tests = sorted(
        test_name for test_name, outcome in required_test_outcomes.items() if outcome == "failed"
    )
    required_test_failure_details = {
        test_name: _extract_required_test_failure_details(
            required_test=test_name,
            gate_result_map=gate_result_map,
        )
        for test_name in failed_required_tests
    }
    missing_required_failure_details = sorted(
        test_name
        for test_name in failed_required_tests
        if not _has_required_failure_detail_contract(test_name, required_test_failure_details.get(test_name, []))
    )
    if missing_required_failure_details:
        for test_name in missing_required_failure_details:
            required_test_failure_details[test_name] = _build_required_failure_detail_contract_fallback(test_name)
    grader_results: dict[str, str] = {}
    grader_details: dict[str, list[dict]] = {}

    if "contract_validator" in required_graders:
        contract_ok, contract_details = _run_contract_validator(phase_id=phase_id, modules=modules)
        grader_results["contract_validator"] = "pass" if contract_ok else "fail"
        grader_details["contract_validator"] = contract_details

    graders_passed = all(value == "pass" for value in grader_results.values()) if grader_results else True
    acceptance_status = (
        "passed" if not missing_required_tests and not failed_required_tests and graders_passed else "rejected"
    )
    failure_types = _collect_failure_types_from_grader_details(grader_details)
    if missing_required_tests:
        failure_types.append("MISSING_TEST_BINDING")
    if failed_required_tests:
        failure_types.append("REQUIRED_TEST_FAILED")
    if missing_required_failure_details:
        failure_types.extend(
            [
                "UNKNOWN_REQUIRED_TEST_FAILURE",
                "CONTROL_PLANE_MISSING_FAILURE_DETAIL",
            ]
        )
    return {
        "acceptance_status": acceptance_status,
        "missing_required_tests": missing_required_tests,
        "failed_required_tests": failed_required_tests,
        "required_test_outcomes": required_test_outcomes,
        "required_test_failure_details": required_test_failure_details,
        "missing_required_failure_details": missing_required_failure_details,
        "grader_results": grader_results,
        "grader_details": grader_details,
        "failure_types": sorted({str(item) for item in failure_types if str(item).strip()}),
    }


def _is_required_test_satisfied(required_test: str, gate_status_map: dict[str, str]) -> bool:
    aliases = _required_test_aliases(required_test)
    return any(gate_status_map.get(gate_name) == "success" for gate_name in aliases)


def _evaluate_required_test_outcomes(
    *,
    required_tests: set[str],
    gate_status_map: dict[str, str],
) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for required_test in sorted(str(item).strip() for item in required_tests if str(item).strip()):
        aliases = _required_test_aliases(required_test)
        observed_statuses = [
            str(gate_status_map.get(gate_name, "")).strip().lower()
            for gate_name in aliases
            if gate_name in gate_status_map
        ]
        if any(status == "success" for status in observed_statuses):
            outcomes[required_test] = "passed"
        elif observed_statuses:
            outcomes[required_test] = "failed"
        else:
            outcomes[required_test] = "missing"
    return outcomes


def _extract_required_test_failure_details(
    *,
    required_test: str,
    gate_result_map: dict[str, dict],
) -> list[str]:
    details: list[str] = []
    for alias in _required_test_aliases(required_test):
        gate_result = gate_result_map.get(alias)
        if not gate_result or str(gate_result.get("status", "")).strip().lower() == "success":
            continue
        log_file = Path(str(gate_result.get("log_file", "")).strip())
        if not log_file.exists():
            continue
        details.extend(_extract_failure_lines_from_gate_log(log_file))
    deduped: list[str] = []
    seen: set[str] = set()
    metadata = [
        f"required_test={required_test}",
        "failure_type=REQUIRED_TEST_FAILED",
        f"location={_required_test_detail_location(required_test=required_test, gate_result_map=gate_result_map)}",
    ]
    for item in metadata:
        deduped.append(item)
        seen.add(item)
    for item in details:
        normalized = str(item).strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped[:10]


def _required_test_detail_location(*, required_test: str, gate_result_map: dict[str, dict]) -> str:
    for alias in _required_test_aliases(required_test):
        gate_result = gate_result_map.get(alias, {})
        if not gate_result:
            continue
        log_path = str(gate_result.get("log_file", "")).strip()
        if log_path:
            return log_path
    return "unavailable"


def _has_required_failure_detail_contract(required_test: str, details: list[str]) -> bool:
    normalized = [str(item).strip() for item in details if str(item).strip()]
    if not normalized:
        return False
    required_tokens = [
        f"required_test={required_test}",
        "failure_type=",
        "location=",
    ]
    joined = "\n".join(normalized)
    return all(token in joined for token in required_tokens)


def _build_required_failure_detail_contract_fallback(required_test: str) -> list[str]:
    return [
        f"required_test={required_test}",
        "failure_type=UNKNOWN_REQUIRED_TEST_FAILURE",
        "location=unavailable",
        "reason=CONTROL_PLANE_MISSING_FAILURE_DETAIL",
    ]


def _extract_failure_lines_from_gate_log(log_file: Path) -> list[str]:
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    signals: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(token in lowered for token in ("failed", "error", "assert", "traceback", "attributeerror", "exception")):
            signals.append(stripped[:300])
    if not signals:
        signals = [line.strip()[:300] for line in lines[:20] if line.strip()]
    return signals[:10]


def _required_test_aliases(required_test: str) -> list[str]:
    normalized = required_test.strip().lower()
    alias_map = _load_required_test_alias_map()
    return alias_map.get(normalized, [normalized])


def _load_required_test_alias_map() -> dict[str, list[str]]:
    default_alias_map = {
        "unit": ["unit", "regression"],
        "integration": ["integration", "regression"],
        "regression": ["regression"],
        "static_scan": ["static_scan"],
        "benchmark": ["benchmark"],
        "compile": ["compile"],
    }
    policy_file = settings.project_root / "policies" / "test_gate_policy.json"
    if not policy_file.exists():
        return default_alias_map
    try:
        payload = json.loads(policy_file.read_text(encoding="utf-8"))
    except Exception:
        return default_alias_map
    aliases_payload = payload.get("required_test_aliases", {})
    if not isinstance(aliases_payload, dict):
        return default_alias_map
    alias_map = dict(default_alias_map)
    for key, value in aliases_payload.items():
        if not isinstance(value, list):
            continue
        alias_map[str(key).strip().lower()] = [str(item).strip().lower() for item in value if str(item).strip()]
    return alias_map


def _run_contract_validator(*, phase_id: str, modules: list[str]) -> tuple[bool, list[dict]]:
    details: list[dict] = []
    roles = (AgentRole.PLANNER, AgentRole.REVIEWER, AgentRole.DEV, AgentRole.QA)
    for module_name in modules:
        for role in roles:
            result_file = get_result_file(phase_id, role, module_name)
            if not result_file.exists():
                missing_type = f"MISSING_{role.value.upper()}_RESULT"
                details.append(
                    {
                        "module": module_name,
                        "agent_role": role.value,
                        "error": "result_file_missing",
                        "failure_type": missing_type,
                    }
                )
                return False, details
            payload_text = result_file.read_text(encoding="utf-8").strip()
            try:
                validate_output_contract(role, payload_text)
            except Exception as exc:
                details.append(
                    {
                        "module": module_name,
                        "agent_role": role.value,
                        "error": "contract_validation_failed",
                        "reason": str(exc),
                        "failure_type": f"INVALID_{role.value.upper()}_CONTRACT",
                    }
                )
                return False, details
            if settings.codex_fail_on_state_db_warning and _has_state_db_warning(phase_id=phase_id, role=role):
                details.append(
                    {
                        "module": module_name,
                        "agent_role": role.value,
                        "error": "state_db_degraded",
                        "reason": "state_db_falling_back_detected_in_runner_log",
                        "failure_type": "STATE_DB_DEGRADED",
                    }
                )
                return False, details
            if _has_silent_failure(payload_text=payload_text):
                details.append(
                    {
                        "module": module_name,
                        "agent_role": role.value,
                        "error": "silent_failure_detected",
                        "reason": "success_exit_with_embedded_error_payload",
                        "failure_type": f"SILENT_{role.value.upper()}_FAILURE",
                    }
                )
                return False, details
    return True, details


def _has_state_db_warning(*, phase_id: str, role: AgentRole) -> bool:
    log_file = settings.logs_dir / f"{phase_id}_{role.value}.log"
    if not log_file.exists():
        return False
    content = log_file.read_text(encoding="utf-8", errors="replace").lower()
    return "falling_back" in content and "state db" in content


def _has_silent_failure(*, payload_text: str) -> bool:
    payload = _safe_contract_parse(payload_text)
    if not payload:
        return False
    status_value = str(payload.get("status", "")).strip().lower()
    if status_value in {"failed", "fail", "error"}:
        return True
    issues_value = payload.get("issues", [])
    if isinstance(issues_value, list) and issues_value:
        return True
    return False


def _is_non_retryable_error(error_message: str) -> bool:
    lowered = (error_message or "").lower()
    non_retryable_signals = (
        "usage limit",
        "hit your usage limit",
        "quota",
        "rate limit",
        "429",
        "insufficient_quota",
    )
    return any(signal in lowered for signal in non_retryable_signals)


def _write_failure_contract_result(
    *,
    result_file: Path,
    agent_role: AgentRole,
    module_name: str | None,
    reason: str,
    failure_type: str = "",
    preserve_existing: bool = True,
) -> bool:
    result_file.parent.mkdir(parents=True, exist_ok=True)
    if preserve_existing and result_file.exists():
        existing_text = result_file.read_text(encoding="utf-8").strip()
        if existing_text:
            _append_failure_metadata(
                result_file=result_file,
                reason=reason,
                failure_type=failure_type or _infer_failure_type(agent_role=agent_role, error_message=reason),
            )
            return False
    module = module_name or "module_main"
    generated_at = datetime.now(timezone.utc).isoformat()
    payload: dict
    if agent_role == AgentRole.PLANNER:
        payload = {
            "contract_version": "1.0",
            "generated_at": generated_at,
            "constraints_ack": True,
            "module_name": module,
            "plan_summary": f"blocked: {reason[:200]}",
            "tasks": [f"blocked: {reason[:120]}"],
            "acceptance_criteria": [],
        }
    elif agent_role == AgentRole.REVIEWER:
        payload = {
            "contract_version": "1.0",
            "generated_at": generated_at,
            "constraints_ack": True,
            "module_name": module,
            "verdict": "needs_revision",
            "findings": [f"runner_blocked: {reason[:200]}"],
            "finding_codes": ["RUNNER_BLOCKED"],
        }
    elif agent_role == AgentRole.DEV:
        payload = {
            "contract_version": "1.0",
            "generated_at": generated_at,
            "constraints_ack": True,
            "module_name": module,
            "status": "failed",
            "files_changed": [],
            "implementation_notes": f"runner_blocked: {reason[:250]}",
        }
    else:
        payload = {
            "contract_version": "1.0",
            "generated_at": generated_at,
            "constraints_ack": True,
            "module_name": module,
            "status": "fail",
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 1,
            "issues": [f"runner_blocked: {reason[:250]}"],
        }
    try:
        result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_failure_metadata(
            result_file=result_file,
            reason=reason,
            failure_type=failure_type or _infer_failure_type(agent_role=agent_role, error_message=reason),
        )
        return True
    except Exception:
        return False


def _append_failure_metadata(*, result_file: Path, reason: str, failure_type: str) -> None:
    metadata_file = result_file.with_name(f"{result_file.stem}.meta.json")
    payload = {
        "failure_events": [],
    }
    if metadata_file.exists():
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {"failure_events": []}
    events = payload.get("failure_events", [])
    if not isinstance(events, list):
        events = []
    events.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "failure_type": failure_type,
            "reason": reason[:500],
        }
    )
    payload["failure_events"] = events[-20:]
    metadata_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _missing_required_artifacts(*, phase_id: str, module_name: str | None, repo_root: Path) -> list[str]:
    if not module_name:
        return []
    spec_file = get_contract_file(phase_id, module_name, "acceptance_spec")
    if not spec_file.exists():
        return []
    try:
        payload = json.loads(spec_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    required_artifacts = payload.get("required_artifacts", [])
    if not isinstance(required_artifacts, list):
        return []
    missing: list[str] = []
    for artifact in required_artifacts:
        path_text = str(artifact).strip()
        if not path_text:
            continue
        candidate = Path(path_text)
        artifact_path = candidate if candidate.is_absolute() else (repo_root / candidate)
        if not artifact_path.exists():
            missing.append(path_text)
    return missing


def _extract_missing_artifacts(error_message: str) -> list[str]:
    marker = "missing_required_artifacts:"
    lowered = (error_message or "").lower()
    if marker not in lowered:
        return []
    _, _, suffix = (error_message or "").partition(marker)
    return [item.strip() for item in suffix.split(",") if item.strip()]


def _truncate_text(value: object, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _extract_subprocess_failure_detail(*, result: AgentRunResult | None, error_message: str) -> dict:
    if result is None:
        return {
            "exit_code": "",
            "error_message": _truncate_text(error_message, 500),
            "stderr_tail": "",
            "stdout_tail": "",
            "execution_mode": "",
            "session_source": "",
            "session_scope": "",
        }
    artifacts = dict(result.artifacts or {})
    return {
        "exit_code": int(result.exit_code),
        "error_message": _truncate_text(error_message or result.error_message or "", 500),
        "stderr_tail": _truncate_text(result.stderr or "", 300),
        "stdout_tail": _truncate_text(result.stdout or "", 300),
        "execution_mode": _truncate_text(artifacts.get("execution_mode", ""), 80),
        "session_source": _truncate_text(artifacts.get("session_source", ""), 80),
        "session_scope": _truncate_text(artifacts.get("session_scope", ""), 120),
    }


def _infer_failure_type(
    *,
    agent_role: AgentRole,
    error_message: str,
    result: AgentRunResult | None = None,
    output_text: str = "",
    contract_valid: bool | None = None,
    contract_error: str = "",
) -> str:
    lowered = (error_message or "").lower()
    if "agent_total_timeout_exceeded" in lowered or "timeout" in lowered:
        return "GLOBAL_TIMEOUT"
    if "state db" in lowered or "falling_back" in lowered or "state_db" in lowered:
        return "AGENT_RUNNER_SESSION_DEGRADED"
    if "missing_required_artifacts:" in lowered:
        return "MISSING_DEV_ARTIFACT" if agent_role == AgentRole.DEV else "MISSING_QA_ARTIFACT"
    if "result_file_missing_or_empty" in lowered:
        return "AGENT_ARTIFACT_WRITE_FAILED"
    if not output_text.strip():
        return "AGENT_OUTPUT_MISSING"
    if output_text and not _safe_contract_parse(output_text):
        return "AGENT_RESULT_PARSE_FAILED"
    if contract_valid is False and ("contract" in lowered or str(contract_error).strip()):
        return "AGENT_CONTRACT_VIOLATION"
    if result is not None and int(result.exit_code) not in {0}:
        return "AGENT_SUBPROCESS_NONZERO_EXIT"
    if _is_non_retryable_error(error_message):
        return "RUNNER_USAGE_LIMIT"
    if "blocked_by_reviewer" in lowered:
        return "BLOCKED_BY_REVIEWER"
    if "blocked_by_planner" in lowered:
        return "BLOCKED_BY_PLANNER"
    if "contract" in lowered:
        return "AGENT_CONTRACT_VIOLATION"
    return "AGENT_EXECUTION_FAILED"


def _infer_failure_severity(error_message: str) -> str:
    if _is_non_retryable_error(error_message):
        return "soft_fail"
    return "hard_fail"


def _collect_failure_types_from_grader_details(grader_details: dict[str, list[dict]]) -> list[str]:
    failure_types: set[str] = set()
    for entries in grader_details.values():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            failure_type = str(item.get("failure_type", "")).strip()
            if failure_type:
                failure_types.add(failure_type)
    return sorted(failure_types)


def _append_runtime_event(
    *,
    project_id: str,
    phase_id: str,
    stage: str,
    actor: str,
    event_type: str,
    failure_type: str | None = None,
    cause_class: str = "",
    payload: dict | None = None,
    artifact_refs: list[str] | None = None,
) -> None:
    try:
        event_store = EventStore()
        event_id = f"{project_id}.{phase_id}.{stage}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        event_store.append(
            EventRecord(
                event_id=event_id,
                event_time=datetime.now().isoformat(),
                workflow_id=project_id,
                run_id=project_id,
                phase_id=phase_id,
                stage=stage,
                actor=actor,
                event_type=event_type,
                cause_class=cause_class,
                failure_type=failure_type,
                payload=payload or {},
                artifact_refs=artifact_refs or [],
                trace_id=f"{project_id}:{phase_id}",
            )
        )
    except Exception:
        return


def _event_type_from_failure_type(failure_type: str) -> str:
    code = str(failure_type).strip().upper()
    if code in {"RUNNER_BLOCKED", "STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT", "AGENT_RUNNER_SESSION_DEGRADED"}:
        return "RUNNER_DEGRADED"
    if code == "GLOBAL_TIMEOUT":
        return "STAGE_TIMEOUT"
    if code.startswith("INVALID_"):
        return "CONTRACT_LINT_FAILED"
    if code == "AGENT_CONTRACT_VIOLATION":
        return "CONTRACT_LINT_FAILED"
    if code.startswith("MISSING_") and code.endswith("_ARTIFACT"):
        return "ARTIFACT_MISSING"
    if code in {"PATH_CONFLICT", "MISSING_TEST_BINDING", "MISSING_REQUIRED_TEST"}:
        return "REVIEW_FINDING_EMITTED"
    if code.startswith("AGENT_"):
        return "STAGE_HARD_FAILED"
    return "STAGE_SOFT_FAILED"


def _cause_class_from_failure_type(failure_type: str) -> str:
    code = str(failure_type).strip().upper()
    if code in {"PATH_CONFLICT", "MISSING_TEST_BINDING", "GRADER_FAILED", "REVIEW_NEEDS_REVISION"}:
        return "business"
    if code in {"RUNNER_BLOCKED", "GLOBAL_TIMEOUT", "AGENT_EXECUTION_FAILED", "MODULE_PIPELINE_FAILED"}:
        return "execution"
    if code in {"STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT", "AGENT_RUNNER_SESSION_DEGRADED"}:
        return "environment"
    if code in {"AGENT_OUTPUT_MISSING", "AGENT_RESULT_PARSE_FAILED", "AGENT_SUBPROCESS_NONZERO_EXIT", "AGENT_ARTIFACT_WRITE_FAILED"}:
        return "execution"
    if code == "AGENT_CONTRACT_VIOLATION":
        return "contract"
    if code.startswith("INVALID_") or code.startswith("MISSING_") or code == "MISSING_REQUIRED_TEST":
        return "contract"
    return "unknown"


def _evaluate_dev_path_guard(
    *,
    phase_id: str,
    module_name: str | None,
    contract_payload: dict,
    repo_root: Path,
) -> dict:
    if not module_name:
        return {"ok": True, "invalid_paths": []}

    change_spec_file = get_contract_file(phase_id, module_name, "change_spec")
    if not change_spec_file.exists():
        return {"ok": True, "invalid_paths": []}

    try:
        change_spec = json.loads(change_spec_file.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "invalid_paths": ["<invalid_change_spec>"]}

    claimed_paths = contract_payload.get("files_changed", [])
    if not isinstance(claimed_paths, list):
        return {"ok": False, "invalid_paths": ["<invalid_files_changed>"]}

    allowed_patterns = change_spec.get("allowed_paths", [])
    guard = validate_claimed_paths(
        claimed_paths=[str(path) for path in claimed_paths],
        allowed_patterns=[str(pattern) for pattern in allowed_patterns],
        repo_root=repo_root,
    )
    return guard.model_dump(mode="json")
