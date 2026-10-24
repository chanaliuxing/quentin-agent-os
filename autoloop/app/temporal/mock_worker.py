import asyncio
from datetime import datetime

from app.config import settings
from app.control import DecisionPolicy, EnergyScorer
from app.control import write_terminal_event_once
from app.diagnosis import RepairPlanner
from app.evidence import EvidenceRecord, EvidenceStore, EventRecord, EventStore
from app.temporal.activities import (
    read_prd_activity,
    decompose_modules_activity,
    generate_phase_tasks_activity,
    run_module_pipeline_activity,
    collect_results_activity,
    git_overlap_report_activity,
    integration_test_activity,
    write_phase_report_activity,
)
from app.temporal.workflow import (
    _collect_changed_files_from_results,
    _collect_reviewer_codes_from_results,
    _derive_failure_diagnostics,
    _derive_terminal_state,
    _enforce_acceptance_from_pipeline_outcome,
    _event_type_for_failure,
    _build_temporal_gate_suite,
    _build_temporal_invariant_report,
    _execute_temporal_repair,
    _recommend_recovery_action,
    _should_stop_on_halt,
    _write_human_review_hook,
)
from app.workspace import resolve_workspace_identity


class MockTemporalWorker:
    async def run_workflow(self, project_id: str, prd_path: str) -> dict:
        print(f"[Mock Temporal] Running workflow for project: {project_id}")

        prd_content = await read_prd_activity(prd_path)
        print(f"[Mock Temporal] Read PRD: {len(prd_content)} chars")

        phase_id = "phase_01"
        modules = await decompose_modules_activity(project_id, phase_id, prd_content)
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
        event_store = EventStore()
        event_seq = 0
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

        while control_round <= settings.max_review_loops_per_module and pending_modules:
            failed_modules = []
            module_failure_details: list[dict] = []
            pending_name_set = {module["name"] for module in pending_modules}
            for level in module_levels:
                level_modules = [module for module in level if module["name"] in pending_name_set]
                if not level_modules:
                    continue
                generated_tasks = await asyncio.gather(
                    *[
                        generate_phase_tasks_activity(project_id, phase_id, prd_content, module["name"])
                        for module in level_modules
                    ]
                )
                for task_result in generated_tasks:
                    print(f"[Mock Temporal] Generated tasks: {task_result}")

                module_pipeline_results = await asyncio.gather(
                    *[
                        run_module_pipeline_activity(project_id, phase_id, module["name"])
                        for module in level_modules
                    ]
                )
                for module, module_result in zip(level_modules, module_pipeline_results):
                    print(
                        f"[Mock Temporal] Pipeline result ({module['name']}): {module_result.get('status')}"
                    )
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
                                }
                            )

            final_results = await collect_results_activity(project_id, phase_id, module_names)
            print(f"[Mock Temporal] Collected {len(final_results)} results")

            final_overlap_report = await git_overlap_report_activity(project_id, phase_id)
            print(f"[Mock Temporal] Overlap report: {final_overlap_report['overlaps_count']} overlaps")

            final_test_results = await integration_test_activity(project_id, phase_id, module_names)
            print(f"[Mock Temporal] Integration tests: {final_test_results['status']}")
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

            final_phase_report = await write_phase_report_activity(
                project_id, phase_id, final_results, final_overlap_report, final_test_results
            )
            print(f"[Mock Temporal] Phase report written to: {final_phase_report}")

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

        status = (
            "completed"
            if (
                final_decision is not None
                and final_decision.decision.value == "advance"
                and final_acceptance_status == "passed"
            )
            else "failed"
        )
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


def _topological_levels(modules: list[dict]) -> list[list[dict]]:
    module_map = {m["name"]: m for m in modules}
    indegree = {name: 0 for name in module_map}
    adjacency: dict[str, list[str]] = {name: [] for name in module_map}
    for module in modules:
        for dep in module.get("depends_on", []):
            dep_name = str(dep)
            if dep_name in module_map:
                indegree[module["name"]] += 1
                adjacency[dep_name].append(module["name"])

    queue = [name for name, degree in indegree.items() if degree == 0]
    levels: list[list[dict]] = []
    while queue:
        current_level = list(queue)
        queue = []
        levels.append([module_map[name] for name in current_level])
        for name in current_level:
            for nxt in adjacency[name]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

    total = sum(len(level) for level in levels)
    if total != len(modules):
        return [modules]
    return levels
