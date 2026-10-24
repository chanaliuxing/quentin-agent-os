import json
from datetime import datetime, timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.control import DecisionPolicy, EnergyScorer, route_recovery_action
    from app.control import write_terminal_event_once
    from app.evidence import (
        EvidenceRecord,
        EvidenceStore,
        EventRecord,
        EventStore,
    )
    from app.diagnosis import RepairPlanner
    from app.models import AgentRole, AgentStatus, PhaseState, ProjectState, extract_json_payload
    from app.models import GateResult, GateStatus, GateSuiteResult, RepairDecision
    from app.rollback import RollbackManager, derive_module_context, select_modules_for_repair
    from app.sor import InvariantReport, InvariantViolation, SorRepository, module_ids_from_scope_tokens
    from app.workspace import resolve_workspace_identity, split_claimed_paths
    from app.config import settings
    from app.temporal.activities import (
        read_prd_activity,
        decompose_modules_activity,
        generate_phase_tasks_activity,
        run_agent_activity,
        run_module_pipeline_activity,
        collect_results_activity,
        git_overlap_report_activity,
        integration_test_activity,
        write_phase_report_activity,
    )


@workflow.defn
class RunProjectWorkflow:
    @workflow.run
    async def run(self, project_id: str, prd_path: str) -> dict:
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=10),
        )

        prd_content = await workflow.execute_activity(
            read_prd_activity,
            prd_path,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry_policy,
        )

        phase_id = "phase_01"

        modules = await workflow.execute_activity(
            decompose_modules_activity,
            args=[project_id, phase_id, prd_content],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry_policy,
        )
        module_levels = _topological_levels(modules)
        module_order = [module for level in module_levels for module in level]
        module_names = [m["name"] for m in module_order]

        control_round = 0
        pending_modules = module_order
        previous_energy = None
        failed_modules: list[dict] = []
        repair_history: list[dict] = []
        repair_execution_history: list[dict] = []
        energy_history: list[dict] = []
        final_results: dict = {}
        final_overlap_report: dict = {}
        final_test_results: dict = {}
        final_phase_report = ""
        final_evidence_file = ""
        final_decision = None
        final_energy = None
        final_acceptance_status = "not_evaluated"
        final_recommended_action = "escalate_to_human"
        final_terminal_state = "REJECTED"
        failure_signature_counts: dict[str, int] = {}
        event_seq = 0
        event_store = EventStore()
        event_log_file = ""
        phase_events: list[dict] = []

        event_seq += 1
        event_log_file = str(
            event_store.append(
                EventRecord(
                    event_id=f"{project_id}.{phase_id}.workflow.{event_seq:03d}",
                    event_time=datetime.now().isoformat(),
                    workflow_id=project_id,
                    run_id=project_id,
                    phase_id=phase_id,
                    stage="workflow",
                    actor="workflow",
                    event_type="WORKFLOW_STARTED",
                    cause_class="terminal",
                    trace_id=f"{project_id}:{phase_id}",
                )
            )
        )
        event_seq += 1
        event_store.append(
            EventRecord(
                event_id=f"{project_id}.{phase_id}.phase.{event_seq:03d}",
                event_time=datetime.now().isoformat(),
                workflow_id=project_id,
                run_id=project_id,
                phase_id=phase_id,
                stage=phase_id,
                actor="workflow",
                event_type="PHASE_STARTED",
                cause_class="terminal",
                trace_id=f"{project_id}:{phase_id}",
            )
        )

        while control_round <= settings.max_review_loops_per_module and pending_modules:
            failed_modules = []
            module_failure_details: list[dict] = []
            pending_name_set = {module["name"] for module in pending_modules}
            for level in module_levels:
                level_modules = [module for module in level if module["name"] in pending_name_set]
                if not level_modules:
                    continue
                task_handles = []
                for module in level_modules:
                    event_seq += 1
                    event_store.append(
                        EventRecord(
                            event_id=f"{project_id}.{phase_id}.{module['name']}.{event_seq:03d}",
                            event_time=datetime.now().isoformat(),
                            workflow_id=project_id,
                            run_id=project_id,
                            phase_id=phase_id,
                            stage="planner",
                            actor="activity",
                            event_type="STAGE_STARTED",
                            cause_class="execution",
                            payload={"module": module["name"], "activity": "generate_phase_tasks"},
                            trace_id=f"{project_id}:{phase_id}:{control_round}",
                        )
                    )
                    task_handles.append(
                        workflow.start_activity(
                            generate_phase_tasks_activity,
                            args=[project_id, phase_id, prd_content, module["name"]],
                            start_to_close_timeout=timedelta(seconds=120),
                            retry_policy=retry_policy,
                        )
                    )
                for handle in task_handles:
                    await handle

                pipeline_handles = []
                for module in level_modules:
                    event_seq += 1
                    event_store.append(
                        EventRecord(
                            event_id=f"{project_id}.{phase_id}.{module['name']}.{event_seq:03d}",
                            event_time=datetime.now().isoformat(),
                            workflow_id=project_id,
                            run_id=project_id,
                            phase_id=phase_id,
                            stage="workflow",
                            actor="activity",
                            event_type="STAGE_STARTED",
                            cause_class="execution",
                            payload={"module": module["name"], "activity": "run_module_pipeline"},
                            trace_id=f"{project_id}:{phase_id}:{control_round}",
                        )
                    )
                    pipeline_handles.append(
                        workflow.start_activity(
                            run_module_pipeline_activity,
                            args=[project_id, phase_id, module["name"]],
                            start_to_close_timeout=timedelta(seconds=1800),
                            retry_policy=retry_policy,
                        )
                    )
                for module, handle in zip(level_modules, pipeline_handles):
                    module_result = await handle
                    if module_result.get("status") != "success":
                        failed_modules.append(module)
                        for role_key in ("planner_result", "reviewer_result", "dev_result", "qa_result"):
                            role_result = module_result.get(role_key, {})
                            if not isinstance(role_result, dict):
                                continue
                            failure_type = str(role_result.get("failure_type", "")).strip()
                            if not failure_type:
                                continue
                            owner_agent = str(role_key).replace("_result", "")
                            module_failure_details.append(
                                {
                                    "module_name": str(module.get("name", "")),
                                    "failure_type": failure_type,
                                    "stage": f"{owner_agent}_handoff_failed",
                                    "owner_agent": owner_agent,
                                    "first_failure_at": datetime.now().isoformat(),
                                    "payload": {
                                        "error": str(role_result.get("error", "")).strip(),
                                        "exit_code": role_result.get("exit_code"),
                                        "failure_detail": dict(role_result.get("failure_detail", {}) or {}),
                                        "runner_artifacts": dict(role_result.get("runner_artifacts", {}) or {}),
                                    },
                                }
                            )

            final_results = await workflow.execute_activity(
                collect_results_activity,
                args=[project_id, phase_id, module_names],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=retry_policy,
            )

            final_overlap_report = await workflow.execute_activity(
                git_overlap_report_activity,
                args=[project_id, phase_id],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=retry_policy,
            )

            final_test_results = await workflow.execute_activity(
                integration_test_activity,
                args=[project_id, phase_id, module_names],
                start_to_close_timeout=timedelta(seconds=600),
                retry_policy=retry_policy,
            )

            missing_results = any(
                "No result file found" in str(module_results.get(agent, ""))
                for module_results in final_results.values()
                for agent in ("planner", "reviewer", "dev", "qa")
            )
            final_test_results, final_acceptance_status = _enforce_acceptance_from_pipeline_outcome(
                test_results=final_test_results,
                failed_modules=failed_modules,
                missing_results=missing_results,
            )
            final_phase_report = await workflow.execute_activity(
                write_phase_report_activity,
                args=[project_id, phase_id, final_results, final_overlap_report, final_test_results],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=retry_policy,
            )
            reviewer_codes = _collect_reviewer_codes_from_results(final_results)
            phase_events = event_store.read(project_id, phase_id)
            failure_diagnostics = _derive_failure_diagnostics(
                results=final_results,
                test_results=final_test_results,
                failed_modules=failed_modules,
                module_failure_details=module_failure_details,
                events=phase_events,
            )
            for failure_event in failure_diagnostics.get("failure_events", []):
                if not isinstance(failure_event, dict):
                    continue
                event_seq += 1
                event_id = f"{project_id}.{phase_id}.failure.{event_seq:03d}"
                event = EventRecord(
                    event_id=event_id,
                    event_time=str(failure_event.get("event_time", datetime.now().isoformat())),
                    workflow_id=project_id,
                    run_id=project_id,
                    phase_id=phase_id,
                    stage=str(failure_event.get("stage", "workflow")),
                    actor=str(failure_event.get("actor", "workflow")),
                    event_type=_event_type_for_failure(str(failure_event.get("cause_type", ""))),
                    attempt=int(failure_event.get("attempt", 1)),
                    cause_class=str(failure_event.get("cause_class", "unknown")),
                    failure_type=str(failure_event.get("cause_type", "")) or None,
                    payload={"is_primary_candidate": bool(failure_event.get("is_primary_candidate", True))},
                    trace_id=f"{project_id}:{phase_id}:{control_round}",
                )
                event_store.append(event)
                phase_events.append(event.model_dump(mode="json"))
                if (
                    not str(failure_diagnostics.get("first_failure_event_id", "")).strip()
                    and str(failure_event.get("cause_type", "")).strip()
                    == str(failure_diagnostics.get("primary_failure_type", "")).strip()
                ):
                    failure_diagnostics["first_failure_event_id"] = event_id
            failure_signature = failure_diagnostics.get("failure_signature", "")
            if failure_signature:
                failure_signature_counts[failure_signature] = (
                    failure_signature_counts.get(failure_signature, 0) + 1
                )
            round_recommended_action = _recommend_recovery_action(
                status="completed" if final_acceptance_status == "passed" else "failed",
                acceptance_status=final_acceptance_status,
                failed_modules=[m["name"] for m in failed_modules],
                replan_rounds=control_round,
                reviewer_codes=reviewer_codes,
                failure_type=str(failure_diagnostics.get("primary_failure_type", "")),
                first_failure_stage=str(failure_diagnostics.get("first_failure_stage", "")),
                failure_signature_count=failure_signature_counts.get(failure_signature, 0),
            )
            final_recommended_action = round_recommended_action
            event_seq += 1
            event_store.append(
                EventRecord(
                    event_id=f"{project_id}.{phase_id}.recovery.{event_seq:03d}",
                    event_time=datetime.now().isoformat(),
                    workflow_id=project_id,
                    run_id=project_id,
                    phase_id=phase_id,
                    stage="workflow",
                    actor="workflow",
                    event_type="RECOVERY_DECIDED",
                    cause_class="recovery",
                    payload={"recommended_action": round_recommended_action},
                    trace_id=f"{project_id}:{phase_id}:{control_round}",
                )
            )
            final_terminal_state = _derive_terminal_state(
                acceptance_status=final_acceptance_status,
                recommended_action=round_recommended_action,
                failure_diagnostics=failure_diagnostics,
            )
            workspace_identity = resolve_workspace_identity(settings.project_root)
            evidence_record = EvidenceRecord(
                record_id=f"evidence_{phase_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                run_id=project_id,
                phase_id=phase_id,
                workflow_version="convergence-v1",
                module_ids=module_names,
                base_sha=workspace_identity.base_sha,
                head_sha=workspace_identity.head_sha,
                acceptance_status=final_acceptance_status,
                test_status=str(final_test_results.get("status", "unknown")),
                missing_required_tests=[
                    str(item) for item in final_test_results.get("missing_required_tests", [])
                ],
                failed_required_tests=[
                    str(item) for item in final_test_results.get("failed_required_tests", [])
                ],
                required_test_outcomes={
                    str(key): str(value)
                    for key, value in final_test_results.get("required_test_outcomes", {}).items()
                },
                required_test_failure_details={
                    str(key): [str(item) for item in value if str(item).strip()]
                    for key, value in final_test_results.get("required_test_failure_details", {}).items()
                    if isinstance(value, list)
                },
                grader_results={
                    str(key): str(value)
                    for key, value in final_test_results.get("grader_results", {}).items()
                },
                grader_details={
                    str(key): [dict(item) for item in value if isinstance(item, dict)]
                    for key, value in final_test_results.get("grader_details", {}).items()
                    if isinstance(value, list)
                },
                changed_files=_collect_changed_files_from_results(final_results),
                first_failure_stage=str(failure_diagnostics.get("first_failure_stage", "")),
                failure_type=str(failure_diagnostics.get("primary_failure_type", "")),
                primary_failure_type=str(failure_diagnostics.get("primary_failure_type", "")),
                secondary_failure_types=[
                    str(item) for item in failure_diagnostics.get("secondary_failure_types", [])
                ],
                failure_signature=str(failure_diagnostics.get("failure_signature", "")),
                owner_agent=str(failure_diagnostics.get("owner_agent", "")),
                missing_artifacts=[str(item) for item in failure_diagnostics.get("missing_artifacts", [])],
                first_failure_at=str(failure_diagnostics.get("first_failure_at", "")),
                first_failure_event_id=str(failure_diagnostics.get("first_failure_event_id", "")),
                final_status_label=str(failure_diagnostics.get("final_status_label", "")),
                terminal_state=final_terminal_state,
                failure_events=[
                    dict(item)
                    for item in failure_diagnostics.get("failure_events", [])
                    if isinstance(item, dict)
                ],
                event_log_file=event_log_file,
                trace_id=f"{project_id}:{phase_id}:{control_round}",
            )
            final_evidence_file = str(EvidenceStore().record(evidence_record))

            gate_suite = _build_temporal_gate_suite(
                project_id=project_id,
                phase_id=phase_id,
                modules=module_order,
                test_results=final_test_results,
                overlap_report=final_overlap_report,
                failed_modules=failed_modules,
            )
            invariant_report = _build_temporal_invariant_report(
                project_id=project_id,
                failed_modules=failed_modules,
            )
            scorer = EnergyScorer()
            final_energy = scorer.from_gate_suite(gate_suite, invariant_report)
            final_decision = DecisionPolicy().decide(previous=previous_energy, current=final_energy)
            scorer.update_calibration(
                weighted_score=final_energy.weighted_score,
                succeeded=final_decision.decision.value == "advance",
            )
            energy_history.append(final_energy.model_dump(mode="json"))

            if round_recommended_action == "advance":
                break

            if control_round >= settings.max_review_loops_per_module:
                break

            if round_recommended_action == "retry_same_plan":
                pending_modules = failed_modules if failed_modules else module_order
                previous_energy = final_energy
                control_round += 1
                continue

            if round_recommended_action == "escalate_to_human":
                break

            repair_decision = RepairPlanner().plan(final_energy)
            repair_history.append(repair_decision.model_dump(mode="json"))
            if final_decision.decision.value == "halt" and _should_stop_on_halt(repair_decision):
                break
            pending_modules, repair_execution = _execute_temporal_repair(
                project_id=project_id,
                phase_id=phase_id,
                modules=module_order,
                failed_modules=failed_modules,
                repair_decision=repair_decision,
            )
            repair_execution_history.append(repair_execution)
            previous_energy = final_energy
            control_round += 1

        status = "failed"
        if (
            final_decision is not None
            and final_decision.decision.value == "advance"
            and final_acceptance_status == "passed"
        ):
            status = "completed"
        if (
            status != "completed"
            and control_round >= settings.max_review_loops_per_module
            and final_recommended_action != "advance"
        ):
            final_recommended_action = "escalate_to_human"
        human_review_hook = ""
        if final_recommended_action == "escalate_to_human":
            human_review_hook = _write_human_review_hook(
                project_id=project_id,
                phase_id=phase_id,
                prd_path=prd_path,
                acceptance_status=final_acceptance_status,
                failed_modules=[m["name"] for m in failed_modules],
                evidence_file=final_evidence_file,
                replan_rounds=control_round,
                trace_id=evidence_record.trace_id,
            )
        termination = write_terminal_event_once(
            project_id=project_id,
            phase_id=phase_id,
            terminal_state=final_terminal_state,
            final_status_label=(
                str(failure_diagnostics.get("final_status_label", ""))
                if "failure_diagnostics" in locals()
                else "UNKNOWN"
            ),
            recommended_action=final_recommended_action,
            acceptance_status=final_acceptance_status,
            primary_failure_type=(
                str(failure_diagnostics.get("primary_failure_type", ""))
                if "failure_diagnostics" in locals()
                else ""
            ),
            secondary_failure_types=[
                str(item)
                for item in (
                    failure_diagnostics.get("secondary_failure_types", [])
                    if "failure_diagnostics" in locals()
                    else []
                )
            ],
            failure_events=[
                dict(item)
                for item in (
                    failure_diagnostics.get("failure_events", [])
                    if "failure_diagnostics" in locals()
                    else []
                )
                if isinstance(item, dict)
            ],
            termination_reason=(
                "workflow_completed"
                if status == "completed"
                else f"workflow_{final_terminal_state.lower()}"
            ),
            trace_id=evidence_record.trace_id if "evidence_record" in locals() else f"{project_id}:{phase_id}",
        )
        summary_path = str(termination.get("execution_summary_file", ""))
        return {
            "project_id": project_id,
            "phase_id": phase_id,
            "status": status,
            "acceptance_status": final_acceptance_status,
            "terminal_state": final_terminal_state,
            "recommended_action": final_recommended_action,
            "phase_report": final_phase_report,
            "evidence_file": final_evidence_file,
            "event_log_file": event_log_file,
            "execution_summary_file": summary_path,
            "terminal_event_id": str(termination.get("terminal_event_id", "")),
            "human_review_hook": human_review_hook,
            "failed_modules": [m["name"] for m in failed_modules],
            "replan_rounds": control_round,
            "energy": final_energy.model_dump(mode="json") if final_energy else {},
            "decision": final_decision.model_dump(mode="json") if final_decision else {},
            "energy_history": energy_history,
            "repair_history": repair_history,
            "repair_execution_history": repair_execution_history,
        }


def _topological_sort(modules: list[dict]) -> list[dict]:
    return [module for level in _topological_levels(modules) for module in level]


def _collect_changed_files_from_results(results: dict) -> list[str]:
    changed_files: list[str] = []
    repo_root = settings.project_root
    for module_results in results.values():
        dev_payload_text = str(module_results.get("dev", ""))
        try:
            dev_payload = extract_json_payload(dev_payload_text)
        except Exception:
            continue
        files_changed = dev_payload.get("files_changed", [])
        if isinstance(files_changed, list):
            filtered_paths, _ignored_paths = split_claimed_paths(
                claimed_paths=[str(path) for path in files_changed],
                repo_root=repo_root,
            )
            changed_files.extend(filtered_paths)
    return changed_files


def _collect_reviewer_codes_from_results(results: dict) -> list[str]:
    codes: list[str] = []
    for module_results in results.values():
        reviewer_payload_text = str(module_results.get("reviewer", ""))
        try:
            reviewer_payload = extract_json_payload(reviewer_payload_text)
        except Exception:
            continue
        payload_codes = reviewer_payload.get("finding_codes", [])
        if isinstance(payload_codes, list):
            codes.extend(str(item) for item in payload_codes)
    deduped = sorted({code for code in codes if code})
    return deduped


def _derive_failure_diagnostics(
    *,
    results: dict,
    test_results: dict,
    failed_modules: list[dict],
    module_failure_details: list[dict] | None = None,
    events: list[dict] | None = None,
) -> dict:
    def _normalize_failure_code(value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"", "none", "null"}:
            return ""
        return text

    event_candidates: list[dict] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        failure_type = _normalize_failure_code(event.get("failure_type", ""))
        if not failure_type:
            continue
        event_time = str(event.get("event_time", "")).strip()
        event_candidates.append(
            {
                "failure_type": failure_type,
                "event_time": event_time,
                "event_id": str(event.get("event_id", "")).strip(),
                "stage": str(event.get("stage", "")).strip(),
                "owner_agent": str(event.get("actor", "")).strip() or "workflow",
                "cause_class": str(event.get("cause_class", _cause_class_for_failure(failure_type))).strip(),
                "payload": dict(event.get("payload", {}) or {}),
            }
        )
    for detail in module_failure_details or []:
        if not isinstance(detail, dict):
            continue
        failure_type = _normalize_failure_code(detail.get("failure_type", ""))
        if not failure_type:
            continue
        event_candidates.append(
            {
                "failure_type": failure_type,
                "event_time": str(detail.get("first_failure_at", "")).strip() or datetime.now().isoformat(),
                "event_id": "",
                "stage": str(detail.get("stage", "")).strip() or "module_pipeline_failed",
                "owner_agent": str(detail.get("owner_agent", "")).strip() or "integrator",
                "cause_class": _cause_class_for_failure(failure_type),
                "payload": dict(detail.get("payload", {}) or {}),
            }
        )
    if event_candidates:
        sorted_candidates = sorted(
            event_candidates,
            key=lambda item: (
                _failure_priority(str(item.get("failure_type", ""))),
                str(item.get("event_time", "")),
            ),
        )
        primary = sorted_candidates[0]
        secondary: list[str] = []
        seen = {str(primary.get("failure_type", ""))}
        for candidate in sorted(event_candidates, key=lambda item: str(item.get("event_time", ""))):
            code = str(candidate.get("failure_type", "")).strip()
            if not code or code in seen:
                continue
            secondary.append(code)
            seen.add(code)
        final_status_label = _derive_final_status_label(
            test_results=test_results,
            candidates=[
                {"failure_type": str(item.get("failure_type", ""))}
                for item in sorted_candidates
            ],
        )
        primary_type = _normalize_primary_failure_type(
            value=str(primary.get("failure_type", "")),
            test_results=test_results,
        )
        primary_type = _promote_business_primary_failure_type(
            primary_type=primary_type,
            first_failure_stage="event_log",
            final_status_label=final_status_label,
            test_results=test_results,
            missing_artifacts=[],
        )
        return _finalize_failure_diagnostics(
            {
            "first_failure_stage": str(primary.get("stage", "")).strip() or "event_log",
            "owner_agent": str(primary.get("owner_agent", "")).strip() or "workflow",
            "primary_failure_type": primary_type,
            "secondary_failure_types": secondary,
            "failure_signature": f"event_log:{primary_type}",
            "missing_artifacts": [],
            "first_failure_at": str(primary.get("event_time", "")),
            "first_failure_event_id": str(primary.get("event_id", "")),
            "final_status_label": final_status_label,
            "failure_events": [
                {
                    "event_time": str(item.get("event_time", "")),
                    "stage": str(item.get("stage", "")),
                    "actor": str(item.get("owner_agent", "")),
                    "attempt": 1,
                    "cause_type": _normalize_failure_code(item.get("failure_type", "")),
                    "cause_class": str(item.get("cause_class", _cause_class_for_failure(_normalize_failure_code(item.get("failure_type", ""))))),
                    "is_primary_candidate": True,
                    "event_id": str(item.get("event_id", "")),
                    "payload": dict(item.get("payload", {}) or {}),
                }
                for item in sorted(event_candidates, key=lambda candidate: str(candidate.get("event_time", "")))
                if _normalize_failure_code(item.get("failure_type", ""))
            ],
            },
            test_results=test_results,
        )

    candidates: list[dict] = []
    observed_index = 0

    def _add_candidate(
        *,
        failure_type: str,
        stage: str,
        owner_agent: str,
        signature: str,
        missing_artifacts: list[str] | None = None,
        first_failure_at: str = "",
        payload: dict | None = None,
    ) -> None:
        nonlocal observed_index
        code = str(failure_type).strip()
        if not code:
            return
        observed_at = str(first_failure_at or datetime.now().isoformat()).strip()
        candidates.append(
            {
                "observed_index": observed_index,
                "priority": _failure_priority(code),
                "failure_type": code,
                "stage": stage,
                "owner_agent": owner_agent,
                "signature": signature,
                "missing_artifacts": sorted(set(missing_artifacts or [])),
                "first_failure_at": observed_at,
                "event_time": observed_at,
                "cause_class": _cause_class_for_failure(code),
                "payload": dict(payload or {}),
            }
        )
        observed_index += 1

    acceptance_failure_types = [str(item).strip() for item in test_results.get("failure_types", []) if str(item).strip()]
    for failure_type in acceptance_failure_types:
        _add_candidate(
            failure_type=failure_type,
            stage="acceptance_contract_failed",
            owner_agent="integrator",
            signature=f"acceptance_contract_failed:{failure_type}",
        )

    for module_name, module_results in results.items():
        for agent in ("planner", "reviewer", "dev", "qa"):
            payload_text = str(module_results.get(agent, ""))
            if "No result file found" in payload_text:
                stage = f"{agent}_output_missing"
                signature = f"{stage}:{module_name}"
                _add_candidate(
                    failure_type=f"MISSING_{agent.upper()}_RESULT",
                    stage=stage,
                    owner_agent=agent,
                    signature=signature,
                )
                continue
            try:
                payload = extract_json_payload(payload_text)
            except Exception:
                continue
            payload_generated_at = str(payload.get("generated_at", "")).strip()
            if agent == "reviewer" and str(payload.get("verdict", "")) == "needs_revision":
                codes = payload.get("finding_codes", [])
                normalized_codes = (
                    [str(code).strip() for code in codes if str(code).strip()]
                    if isinstance(codes, list)
                    else []
                )
                if not normalized_codes:
                    normalized_codes = ["REVIEW_NEEDS_REVISION"]
                stage = "review_gate_rejected"
                for code in normalized_codes:
                    _add_candidate(
                        failure_type=code,
                        stage=stage,
                        owner_agent="reviewer",
                        signature=f"{stage}:{module_name}:{code}",
                        first_failure_at=payload_generated_at,
                    )
            if agent in {"dev", "qa"}:
                status_key = "status"
                failed_value = "failed" if agent == "dev" else "fail"
                if str(payload.get(status_key, "")).lower() == failed_value:
                    stage = f"{agent}_contract_failed"
                    missing_artifacts = []
                    if agent == "dev":
                        missing_artifacts = _extract_missing_artifacts_from_payload(payload.get("implementation_notes", ""))
                    if agent == "qa":
                        issues = payload.get("issues", [])
                        if isinstance(issues, list):
                            for issue in issues:
                                missing_artifacts.extend(_extract_missing_artifacts_from_payload(str(issue)))
                    failure_type = (
                        f"MISSING_{agent.upper()}_ARTIFACT"
                        if missing_artifacts
                        else f"{agent.upper()}_CONTRACT_FAILED"
                    )
                    signature = f"{stage}:{module_name}"
                    _add_candidate(
                        failure_type=failure_type,
                        stage=stage,
                        owner_agent=agent,
                        signature=signature,
                        missing_artifacts=missing_artifacts,
                        first_failure_at=payload_generated_at,
                    )

    acceptance_failure_type_set = {
        str(item).strip().upper() for item in acceptance_failure_types if str(item).strip()
    }
    missing_required_tests = [str(x) for x in test_results.get("missing_required_tests", [])]
    if missing_required_tests and "MISSING_TEST_BINDING" not in acceptance_failure_type_set:
        stage = "required_test_missing"
        signature = f"{stage}:{','.join(sorted(missing_required_tests))}"
        _add_candidate(
            failure_type="MISSING_REQUIRED_TEST",
            stage=stage,
            owner_agent="qa",
            signature=signature,
        )

    failed_required_tests = [str(x) for x in test_results.get("failed_required_tests", []) if str(x).strip()]
    if failed_required_tests and "REQUIRED_TEST_FAILED" not in acceptance_failure_type_set:
        stage = "required_test_failed"
        signature = f"{stage}:{','.join(sorted(failed_required_tests))}"
        _add_candidate(
            failure_type="REQUIRED_TEST_FAILED",
            stage=stage,
            owner_agent="qa",
            signature=signature,
        )

    grader_results = {
        str(k): str(v) for k, v in test_results.get("grader_results", {}).items()
    }
    failed_graders = sorted(key for key, value in grader_results.items() if value != "pass")
    if failed_graders:
        stage = "grader_failed"
        signature_parts: list[str] = []
        grader_details = test_results.get("grader_details", {})
        if isinstance(grader_details, dict):
            for grader_name in failed_graders:
                entries = grader_details.get(grader_name, [])
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    detail_code = str(
                        entry.get("failure_type") or entry.get("error") or ""
                    ).strip()
                    if detail_code:
                        signature_parts.append(f"{grader_name}:{detail_code}")
        signature = f"{stage}:{','.join(signature_parts or failed_graders)}"
        _add_candidate(
            failure_type="GRADER_FAILED",
            stage=stage,
            owner_agent="integrator",
            signature=signature,
        )

    if failed_modules:
        names = sorted(str(module.get("name", "")) for module in failed_modules)
        stage = "module_pipeline_failed"
        signature = f"{stage}:{','.join(names)}"
        _add_candidate(
            failure_type="MODULE_PIPELINE_FAILED",
            stage=stage,
            owner_agent="integrator",
            signature=signature,
        )
    for detail in module_failure_details or []:
        if not isinstance(detail, dict):
            continue
        module_name = str(detail.get("module_name", "")).strip() or "unknown_module"
        failure_type = str(detail.get("failure_type", "")).strip()
        if not failure_type:
            continue
        stage = str(detail.get("stage", "")).strip() or "module_pipeline_failed"
        owner_agent = str(detail.get("owner_agent", "")).strip() or "integrator"
        _add_candidate(
            failure_type=failure_type,
            stage=stage,
            owner_agent=owner_agent,
            signature=f"{stage}:{module_name}:{failure_type}",
            first_failure_at=str(detail.get("first_failure_at", "")).strip(),
            payload=dict(detail.get("payload", {}) or {}),
        )

    final_status_label = _derive_final_status_label(test_results=test_results, candidates=candidates)
    if not candidates:
        fallback_primary = _normalize_primary_failure_type(value="", test_results=test_results)
        fallback_primary = _promote_business_primary_failure_type(
            primary_type=fallback_primary,
            first_failure_stage="unclassified_failure",
            final_status_label=final_status_label,
            test_results=test_results,
            missing_artifacts=[],
        )
        fallback_time = datetime.now().isoformat()
        return _finalize_failure_diagnostics(
            {
            "first_failure_stage": "unclassified_failure",
            "owner_agent": "workflow",
            "primary_failure_type": fallback_primary,
            "secondary_failure_types": [],
            "failure_signature": f"unclassified_failure:{fallback_primary}",
            "missing_artifacts": [],
            "first_failure_at": fallback_time,
            "first_failure_event_id": "",
            "final_status_label": final_status_label,
            "failure_events": [
                {
                    "event_id": "",
                    "event_time": fallback_time,
                    "stage": "workflow",
                    "actor": "workflow",
                    "attempt": 1,
                    "cause_type": fallback_primary,
                    "cause_class": _cause_class_for_failure(fallback_primary),
                    "is_primary_candidate": True,
                }
            ],
            },
            test_results=test_results,
        )

    candidates_sorted = sorted(
        candidates,
        key=lambda item: (int(item["priority"]), int(item["observed_index"])),
    )
    primary_candidate = candidates_sorted[0]
    secondary_failure_types = [
        str(item["failure_type"])
        for item in candidates_sorted[1:]
        if str(item.get("failure_type", "")).strip()
    ]
    deduped_secondary = list(dict.fromkeys(secondary_failure_types))
    failure_events = [
        {
            "event_id": "",
            "event_time": str(item.get("event_time", "")),
            "stage": str(item.get("stage", "")),
            "actor": str(item.get("owner_agent", "")),
            "attempt": 1,
            "cause_type": str(item.get("failure_type", "")),
            "cause_class": str(item.get("cause_class", "")),
            "is_primary_candidate": True,
            "payload": dict(item.get("payload", {}) or {}),
        }
        for item in candidates_sorted
    ]

    primary_type = _normalize_primary_failure_type(
        value=str(primary_candidate.get("failure_type", "")),
        test_results=test_results,
    )
    primary_type = _promote_business_primary_failure_type(
        primary_type=primary_type,
        first_failure_stage=str(primary_candidate.get("stage", "")),
        final_status_label=final_status_label,
        test_results=test_results,
        missing_artifacts=[
            str(item) for item in primary_candidate.get("missing_artifacts", []) if str(item).strip()
        ],
    )
    return _finalize_failure_diagnostics(
        {
        "first_failure_stage": str(primary_candidate.get("stage", "")),
        "owner_agent": str(primary_candidate.get("owner_agent", "")),
        "primary_failure_type": primary_type,
        "secondary_failure_types": deduped_secondary,
        "failure_signature": str(primary_candidate.get("signature", "")) or f"derived:{primary_type}",
        "missing_artifacts": [
            str(item) for item in primary_candidate.get("missing_artifacts", []) if str(item).strip()
        ],
        "first_failure_at": str(primary_candidate.get("first_failure_at", "")),
        "first_failure_event_id": "",
        "final_status_label": final_status_label,
        "failure_events": failure_events,
        },
        test_results=test_results,
    )


def _finalize_failure_diagnostics(diagnostics: dict, *, test_results: dict) -> dict:
    acceptance_status = str(test_results.get("acceptance_status", "")).strip().lower()
    if acceptance_status != "passed":
        return diagnostics
    finalized = dict(diagnostics)
    finalized["primary_failure_type"] = ""
    finalized["secondary_failure_types"] = []
    finalized["failure_signature"] = ""
    finalized["missing_artifacts"] = []
    finalized["first_failure_stage"] = ""
    finalized["owner_agent"] = ""
    finalized["first_failure_at"] = ""
    finalized["first_failure_event_id"] = ""
    finalized["failure_events"] = []
    finalized["final_status_label"] = "ACCEPTED"
    return finalized


def _failure_priority(failure_type: str) -> int:
    code = str(failure_type).strip().upper()
    if code == "PATH_CONFLICT":
        return 10
    if code == "MISSING_TEST_BINDING":
        return 20
    if code == "REQUIRED_TEST_FAILED":
        return 25
    if code.startswith("INVALID_") and code.endswith("_CONTRACT"):
        return 30
    if code.startswith("MISSING_") and code.endswith("_RESULT"):
        return 40
    if code.startswith("BUSINESS_"):
        return 45
    if code.startswith("AGENT_"):
        return 48
    if code in {
        "PLANNER_HANDOFF_STATE_MISMATCH",
        "DEV_HANDOFF_STATE_MISMATCH",
        "QA_HANDOFF_STATE_MISMATCH",
    }:
        return 49
    if code == "RUNNER_BLOCKED":
        return 50
    if code == "STATE_DB_DEGRADED":
        return 60
    if code == "GLOBAL_TIMEOUT":
        return 70
    return 100


def _derive_final_status_label(*, test_results: dict, candidates: list[dict]) -> str:
    configured = str(test_results.get("final_status_label", "")).strip()
    if configured:
        return configured
    execution_status = str(test_results.get("execution_status", "")).strip().lower()
    if "timeout" in execution_status:
        return "GLOBAL_TIMEOUT"
    acceptance_status = str(test_results.get("acceptance_status", "")).strip().lower()
    if acceptance_status == "passed":
        return "ACCEPTED"
    candidate_codes = [str(item.get("failure_type", "")).strip().upper() for item in candidates]
    for terminal in ("GLOBAL_TIMEOUT", "RUNNER_BLOCKED", "STATE_DB_DEGRADED"):
        if terminal in candidate_codes:
            return terminal
    if acceptance_status == "rejected":
        return "ACCEPTANCE_REJECTED"
    run_status = str(test_results.get("status", "")).strip().lower()
    if run_status == "failed":
        return "TESTS_FAILED"
    return "UNKNOWN"


def _derive_terminal_state(
    *,
    acceptance_status: str,
    recommended_action: str,
    failure_diagnostics: dict,
) -> str:
    normalized_acceptance = str(acceptance_status).strip().lower()
    if normalized_acceptance == "passed":
        return "ACCEPTED"
    primary = str(failure_diagnostics.get("primary_failure_type", "")).strip().upper()
    secondary = [str(item).strip().upper() for item in failure_diagnostics.get("secondary_failure_types", [])]
    final_label = str(failure_diagnostics.get("final_status_label", "")).strip().upper()
    timeout_signals = {"GLOBAL_TIMEOUT"}
    if primary in timeout_signals or final_label in timeout_signals or any(
        item in timeout_signals for item in secondary
    ):
        return "TIMEOUT"
    if str(recommended_action).strip() == "escalate_to_human":
        return "ABORTED"
    return "REJECTED"


def _enforce_acceptance_from_pipeline_outcome(
    *,
    test_results: dict,
    failed_modules: list[dict],
    missing_results: bool,
) -> tuple[dict, str]:
    normalized = dict(test_results or {})
    acceptance_status = str(normalized.get("acceptance_status", "")).strip().lower()
    if not acceptance_status:
        acceptance_status = "passed" if str(normalized.get("status", "")).strip().lower() == "success" else "rejected"

    pipeline_failed = bool(failed_modules) or bool(missing_results)
    if not pipeline_failed:
        normalized["acceptance_status"] = acceptance_status
        return normalized, acceptance_status

    failure_types = [str(item).strip() for item in normalized.get("failure_types", []) if str(item).strip()]
    if "MODULE_PIPELINE_FAILED" not in failure_types:
        failure_types.append("MODULE_PIPELINE_FAILED")
    if missing_results and "MISSING_RESULT_ARTIFACT" not in failure_types:
        failure_types.append("MISSING_RESULT_ARTIFACT")

    normalized["failure_types"] = sorted(set(failure_types))
    normalized["acceptance_status"] = "rejected"
    normalized["status"] = "failed"
    normalized["execution_status"] = "pipeline_failed"
    return normalized, "rejected"


def _cause_class_for_failure(failure_type: str) -> str:
    code = str(failure_type).strip().upper()
    if code.startswith("BUSINESS_"):
        return "business"
    if code.startswith("UNCLASSIFIED_BUSINESS_"):
        return "business"
    if code.startswith("UNCLASSIFIED_EXECUTION_"):
        return "execution"
    if code.startswith("UNCLASSIFIED_ENVIRONMENT_"):
        return "environment"
    if code in {"PATH_CONFLICT", "MISSING_TEST_BINDING", "REQUIRED_TEST_FAILED", "GRADER_FAILED", "REVIEW_NEEDS_REVISION"}:
        return "business"
    if code in {"RUNNER_BLOCKED", "GLOBAL_TIMEOUT", "AGENT_EXECUTION_FAILED", "MODULE_PIPELINE_FAILED"}:
        return "execution"
    if code in {"PLANNER_HANDOFF_STATE_MISMATCH", "DEV_HANDOFF_STATE_MISMATCH", "QA_HANDOFF_STATE_MISMATCH"}:
        return "contract"
    if code.startswith("AGENT_"):
        if code == "AGENT_RUNNER_SESSION_DEGRADED":
            return "environment"
        if code == "AGENT_CONTRACT_VIOLATION":
            return "contract"
        return "execution"
    if code in {"STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT"}:
        return "infra"
    if code.startswith("INVALID_") or code.startswith("MISSING_") or code in {"MISSING_REQUIRED_TEST", "REQUIRED_TEST_FAILED"}:
        return "contract"
    return "unknown"


def _event_type_for_failure(failure_type: str) -> str:
    code = str(failure_type).strip().upper()
    if code in {"PATH_CONFLICT", "MISSING_TEST_BINDING", "MISSING_REQUIRED_TEST", "REQUIRED_TEST_FAILED"}:
        return "REVIEW_FINDING_EMITTED"
    if code.startswith("INVALID_"):
        return "CONTRACT_LINT_FAILED"
    if code in {"RUNNER_BLOCKED", "STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT"}:
        return "RUNNER_DEGRADED"
    if code == "AGENT_RUNNER_SESSION_DEGRADED":
        return "RUNNER_DEGRADED"
    if code == "GLOBAL_TIMEOUT":
        return "STAGE_TIMEOUT"
    if code == "AGENT_CONTRACT_VIOLATION":
        return "CONTRACT_LINT_FAILED"
    if code.startswith("AGENT_"):
        return "STAGE_HARD_FAILED"
    if code.startswith("MISSING_") and code.endswith("_ARTIFACT"):
        return "ARTIFACT_MISSING"
    if code.startswith("BUSINESS_"):
        return "STAGE_SOFT_FAILED"
    if code.startswith("UNCLASSIFIED_"):
        return "STAGE_HARD_FAILED"
    return "STAGE_SOFT_FAILED"


def _normalize_primary_failure_type(*, value: str, test_results: dict) -> str:
    code = str(value).strip().upper()
    if code and code not in {"NONE", "NULL", "UNKNOWN", "UNKNOWN_FAILURE"}:
        return code
    acceptance_status = str(test_results.get("acceptance_status", "")).strip().lower()
    execution_status = str(test_results.get("execution_status", "")).strip().lower()
    failure_types = [str(item).strip().upper() for item in test_results.get("failure_types", [])]
    if any("STATE_DB" in item for item in failure_types):
        return "UNCLASSIFIED_ENVIRONMENT_FAILURE"
    if "timeout" in execution_status:
        return "UNCLASSIFIED_EXECUTION_FAILURE"
    if acceptance_status == "rejected":
        return "UNCLASSIFIED_BUSINESS_FAILURE"
    if str(test_results.get("status", "")).strip().lower() == "failed":
        return "UNCLASSIFIED_EXECUTION_FAILURE"
    return "UNCLASSIFIED_ENVIRONMENT_FAILURE"


def _promote_business_primary_failure_type(
    *,
    primary_type: str,
    first_failure_stage: str,
    final_status_label: str,
    test_results: dict,
    missing_artifacts: list[str] | None = None,
) -> str:
    code = str(primary_type).strip().upper()
    if code != "UNCLASSIFIED_BUSINESS_FAILURE":
        return code
    if [item for item in (missing_artifacts or []) if str(item).strip()]:
        return "BUSINESS_ARTIFACT_GAP"
    stage = str(first_failure_stage).strip().lower()
    if stage in {"required_test_missing", "required_test_failed", "acceptance_contract_failed"}:
        return "BUSINESS_TEST_POLICY_GAP"
    if stage in {"grader_failed"}:
        return "BUSINESS_GRADER_CONTRACT_GAP"
    if stage in {"review_gate_rejected"}:
        return "BUSINESS_REVIEW_POLICY_GAP"
    failure_types = [str(item).strip().upper() for item in test_results.get("failure_types", []) if str(item).strip()]
    if "MISSING_REQUIRED_TEST" in failure_types:
        return "BUSINESS_TEST_POLICY_GAP"
    if "GRADER_FAILED" in failure_types:
        return "BUSINESS_GRADER_CONTRACT_GAP"
    if str(final_status_label).strip().upper() in {"ACCEPTANCE_REJECTED", "TESTS_FAILED"}:
        return "BUSINESS_REJECTION_UNMAPPED"
    return "BUSINESS_EVIDENCE_MISSING"


def _extract_missing_artifacts_from_payload(text: str) -> list[str]:
    marker = "missing_required_artifacts:"
    lowered = (text or "").lower()
    if marker not in lowered:
        return []
    _, _, suffix = (text or "").partition(marker)
    return [item.strip() for item in suffix.split(",") if item.strip()]


def _recommend_recovery_action(
    *,
    status: str,
    acceptance_status: str,
    failed_modules: list[str],
    replan_rounds: int,
    reviewer_codes: list[str] | None = None,
    failure_type: str = "",
    first_failure_stage: str = "",
    failure_signature_count: int = 0,
) -> str:
    return route_recovery_action(
        status=status,
        acceptance_status=acceptance_status,
        failed_modules=failed_modules,
        replan_rounds=replan_rounds,
        reviewer_codes=reviewer_codes or [],
        failure_type=failure_type,
        first_failure_stage=first_failure_stage,
        failure_signature_count=failure_signature_count,
        max_review_loops=settings.max_review_loops_per_module,
    )


def _apply_failure_circuit_breaker(
    *,
    recommended_action: str,
    failure_signature: str,
    failure_signature_counts: dict[str, int],
) -> str:
    if recommended_action != "retry_same_plan":
        return recommended_action
    if not failure_signature:
        return recommended_action
    if failure_signature_counts.get(failure_signature, 0) >= 2:
        return "replan_from_spec"
    return recommended_action


def _write_human_review_hook(
    *,
    project_id: str,
    phase_id: str,
    prd_path: str,
    acceptance_status: str,
    failed_modules: list[str],
    evidence_file: str,
    replan_rounds: int,
    trace_id: str = "",
) -> str:
    payload = {
        "project_id": project_id,
        "phase_id": phase_id,
        "prd_path": prd_path,
        "status": "human_review_required",
        "acceptance_status": acceptance_status,
        "failed_modules": failed_modules,
        "evidence_file": evidence_file,
        "trace_id": trace_id,
        "replan_rounds": replan_rounds,
        "timestamp": datetime.now().isoformat(),
    }
    hook_path = settings.hooks_dir / f"{phase_id}_human_review_required.json"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(hook_path)


def _topological_levels(modules: list[dict]) -> list[list[dict]]:
    module_map = {m["name"]: m for m in modules}
    indegree = {name: 0 for name in module_map}
    adjacency: dict[str, list[str]] = {name: [] for name in module_map}

    for module in modules:
        name = module["name"]
        for dep in module.get("depends_on", []):
            dep_name = str(dep)
            if dep_name in module_map:
                indegree[name] += 1
                adjacency[dep_name].append(name)

    queue = [name for name, deg in indegree.items() if deg == 0]
    levels: list[list[dict]] = []
    while queue:
        current_batch = list(queue)
        queue = []
        for name in current_batch:
            for nxt in adjacency[name]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        levels.append([module_map[name] for name in current_batch])

    total = sum(len(level) for level in levels)
    if total != len(modules):
        return [modules]
    return levels


def _build_temporal_invariant_report(
    *,
    project_id: str,
    failed_modules: list[dict],
) -> InvariantReport:
    violations = [
        InvariantViolation(
            rule_id="module_execution_success",
            level="error",
            message=f"module {module['name']} failed during execution",
            subject_id=module["name"],
        )
        for module in failed_modules
    ]
    if not violations:
        return InvariantReport(valid=True, violations=[])
    return InvariantReport(valid=False, violations=violations)


def _build_temporal_gate_suite(
    *,
    project_id: str,
    phase_id: str,
    modules: list[dict],
    test_results: dict,
    overlap_report: dict,
    failed_modules: list[dict],
) -> GateSuiteResult:
    gate_results: list[GateResult] = []
    for gate_result in test_results.get("gate_results", []):
        status = gate_result.get("status", "failed")
        gate_results.append(
            GateResult(
                gate_name=gate_result.get("gate", "unknown_gate"),
                status=GateStatus.PASS if status == "success" else GateStatus.FAIL,
                hard_fail=status != "success",
                score=1.0 if status == "success" else 0.0,
                message=gate_result.get("stderr") or gate_result.get("stdout"),
            )
        )

    if overlap_report.get("overlaps_count", 0) > 0:
        risk_levels = {
            str(item.get("risk_level", "medium")).lower()
            for item in overlap_report.get("overlaps", [])
        }
        gate_results.append(
            GateResult(
                gate_name="overlap_guard",
                status=GateStatus.FAIL if "high" in risk_levels else GateStatus.WARN,
                hard_fail="high" in risk_levels,
                score=0.0 if "high" in risk_levels else 0.5,
            )
        )

    if failed_modules:
        gate_results.append(
            GateResult(
                gate_name="module_execution",
                status=GateStatus.FAIL,
                hard_fail=True,
                score=0.0,
            )
        )

    if not gate_results:
        gate_results.append(
            GateResult(
                gate_name="phase_execution",
                status=GateStatus.PASS,
                hard_fail=False,
                score=1.0,
            )
        )

    return GateSuiteResult(
        run_id=project_id,
        phase_id=phase_id,
        module_id=derive_module_context(modules=modules, failed_modules=failed_modules, phase_id=phase_id),
        results=gate_results,
    )


def _select_modules_for_repair(
    *,
    run_id: str,
    modules: list[dict],
    failed_modules: list[dict],
    repair_decision: RepairDecision,
) -> list[dict]:
    selected_modules = select_modules_for_repair(
        modules=modules,
        failed_modules=failed_modules,
        rollback_target_layer=repair_decision.rollback_target_layer.value,
        rollback_scope=repair_decision.rollback_scope,
        affected_modules=repair_decision.affected_modules,
    )
    if repair_decision.rollback_target_layer.value == "implementation":
        return selected_modules

    try:
        spec = SorRepository().load_project_spec(run_id)
        mapped_module_ids = module_ids_from_scope_tokens(
            spec=spec,
            scope_tokens=list(repair_decision.rollback_scope),
        )
    except Exception:
        return selected_modules

    if not mapped_module_ids:
        return selected_modules
    selected_name_set = {module["name"] for module in selected_modules}
    for module_id in mapped_module_ids:
        selected_name_set.add(module_id)
    return [module for module in modules if module["name"] in selected_name_set]


def _execute_temporal_repair(
    *,
    project_id: str,
    phase_id: str,
    modules: list[dict],
    failed_modules: list[dict],
    repair_decision: RepairDecision,
) -> tuple[list[dict], dict]:
    state = ProjectState(project_id=project_id, prd_path="")
    phase = PhaseState(phase_id=phase_id, phase_number=1, status="failed")
    if failed_modules:
        phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.FAILED
        phase.agent_statuses[AgentRole.QA.value] = AgentStatus.FAILED
    else:
        phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.SUCCESS
        phase.agent_statuses[AgentRole.QA.value] = AgentStatus.SUCCESS
    state.phases.append(phase)

    manager = RollbackManager()
    execution = manager.execute(state, repair_decision)
    next_action = manager.next_action_for(repair_decision)
    if next_action == "dispatch_dev":
        pending_modules = _select_modules_for_repair(
            run_id=project_id,
            modules=modules,
            failed_modules=failed_modules,
            repair_decision=repair_decision,
        )
    else:
        pending_modules = modules
    return pending_modules, {
        "next_action": next_action,
        "execution": execution.model_dump(mode="json"),
        "artifacts": dict(state.artifacts),
    }


def _should_stop_on_halt(repair_decision: RepairDecision) -> bool:
    return repair_decision.rollback_target_layer.value not in {"spec", "contract", "task"}
