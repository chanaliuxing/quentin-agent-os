from datetime import datetime
from pathlib import Path
from app.control import DecisionPolicy, EnergyScorer
from app.diagnosis import RepairPlanner
from app.models import (
    ConvergenceAction,
    GateResult,
    GateStatus,
    GateSuiteResult,
    ProjectState,
    AgentRole,
    AgentStatus,
    TaskAssignment,
)
from app.config import settings
from app.rollback import RollbackManager
from app.utils import ensure_phase_dirs, get_task_file, write_task
from app.observability import log_event
from app.observability.metrics import MetricsCollector, MetricsTimer
from app.sor import InvariantReport, InvariantViolation


def _touch_phases(state: ProjectState) -> None:
    state.phases = list(state.phases)


def _touch_artifacts(state: ProjectState) -> None:
    state.artifacts = dict(state.artifacts)


def _touch_energy_history(state: ProjectState) -> None:
    state.energy_history = list(state.energy_history)


def _build_default_repair_decision(state: ProjectState) -> "RepairDecision":
    from app.models import RepairDecision, RollbackTargetLayer

    phase = state.get_current_phase()
    phase_id = phase.phase_id if phase else f"phase_{state.current_phase:02d}"
    module_scope = [phase_id]
    return RepairDecision(
        run_id=state.project_id,
        phase_id=phase_id,
        failure_class="retry_repair",
        rollback_target_layer=RollbackTargetLayer.IMPLEMENTATION,
        rollback_scope=module_scope,
        affected_modules=module_scope,
        required_agents=["dev", "qa"],
        repair_strategy="reset module implementation state and rerun execution",
        confidence=0.7,
    )


def _build_invariant_report(state: ProjectState) -> InvariantReport:
    phase = state.get_current_phase()
    if not phase:
        return InvariantReport(
            valid=False,
            violations=[
                InvariantViolation(
                    rule_id="phase_exists",
                    level="error",
                    message="phase state is missing",
                    subject_id=f"phase_{state.current_phase:02d}",
                )
            ],
        )

    violations: list[InvariantViolation] = []
    required_agents = [AgentRole.DEV.value, AgentRole.QA.value]
    for agent_name in required_agents:
        status = phase.agent_statuses.get(agent_name)
        if status is not None and status != AgentStatus.SUCCESS:
            violations.append(
                InvariantViolation(
                    rule_id="agent_success_required",
                    level="error",
                    message=f"{agent_name} did not complete successfully",
                    subject_id=agent_name,
                )
            )

    return InvariantReport(valid=not violations, violations=violations)


def _test_result_to_gate(test_name: str, status: str) -> GateResult:
    normalized = status.lower()
    if normalized in {"success", "pass", "passed"}:
        return GateResult(gate_name=test_name, status=GateStatus.PASS, hard_fail=False, score=1.0)
    if normalized in {"warn", "warning"}:
        return GateResult(gate_name=test_name, status=GateStatus.WARN, hard_fail=False, score=0.4)
    return GateResult(gate_name=test_name, status=GateStatus.FAIL, hard_fail=True, score=0.0)


def _build_phase_gate_suite(state: ProjectState) -> GateSuiteResult:
    phase = state.get_current_phase()
    phase_id = f"phase_{state.current_phase:02d}"
    if not phase:
        return GateSuiteResult(
            run_id=state.project_id,
            phase_id=phase_id,
            module_id=phase_id,
            results=[
                GateResult(
                    gate_name="phase_presence",
                    status=GateStatus.FAIL,
                    hard_fail=True,
                    score=0.0,
                )
            ],
        )

    gate_results = [
        *(
            [
                GateResult(
                    gate_name="dev_execution",
                    status=GateStatus.PASS if phase.agent_statuses.get(AgentRole.DEV.value) == AgentStatus.SUCCESS else GateStatus.FAIL,
                    hard_fail=phase.agent_statuses.get(AgentRole.DEV.value) != AgentStatus.SUCCESS,
                    score=1.0 if phase.agent_statuses.get(AgentRole.DEV.value) == AgentStatus.SUCCESS else 0.0,
                )
            ]
            if phase.agent_statuses.get(AgentRole.DEV.value) is not None
            else []
        ),
        *(
            [
                GateResult(
                    gate_name="qa_validation",
                    status=GateStatus.PASS if phase.agent_statuses.get(AgentRole.QA.value) == AgentStatus.SUCCESS else GateStatus.FAIL,
                    hard_fail=phase.agent_statuses.get(AgentRole.QA.value) != AgentStatus.SUCCESS,
                    score=1.0 if phase.agent_statuses.get(AgentRole.QA.value) == AgentStatus.SUCCESS else 0.0,
                )
            ]
            if phase.agent_statuses.get(AgentRole.QA.value) is not None
            else []
        ),
    ]

    for overlap in phase.git_overlaps:
        risk = overlap.risk_level.lower()
        gate_results.append(
            GateResult(
                gate_name=f"overlap_{overlap.file_path}",
                status=GateStatus.FAIL if risk == "high" else GateStatus.WARN,
                hard_fail=risk == "high",
                score=0.0 if risk == "high" else 0.5,
                evidence_refs=overlap.commits,
                message="git overlap detected",
            )
        )

    for test_result in phase.test_results:
        gate_results.append(_test_result_to_gate(test_result.test_name, test_result.status))

    return GateSuiteResult(
        run_id=state.project_id,
        phase_id=phase.phase_id,
        module_id=phase.phase_id,
        results=gate_results,
    )


async def lead_plan_node(state: ProjectState) -> ProjectState:
    state.next_action = "lead_plan"
    log_event("lead_plan", phase=state.current_phase, project_id=state.project_id)

    phase_id = f"phase_{state.current_phase:02d}"
    phase = state.get_current_phase()

    if phase is None:
        phase = state.add_phase(phase_id)
        phase.started_at = datetime.now()

    MetricsCollector.increment_workflow_active(phase_id)

    ensure_phase_dirs(phase_id)

    prd_content = Path(state.prd_path).read_text() if Path(state.prd_path).exists() else ""

    dev_task_content = f"""# Dev Task - Phase {state.current_phase}

## Context
This is phase {state.current_phase} of the project implementation.

## PRD Reference
{prd_content[:1000]}...

## Your Tasks
1. Implement the core functionality as described in the PRD
2. Follow coding standards and best practices
3. Write clean, maintainable code
4. Test your implementation locally
5. Commit changes with proper message format

## Constraints
- Work only in your assigned worktree
- Do not modify files outside your scope
- Follow the commit message format: agent:dev phase:{phase_id} module:<name> summary:<changes>

## Deliverables
Write your results to the result.md file with:
- What you implemented
- Files changed
- Any issues or blockers
"""

    qa_task_content = f"""# QA Task - Phase {state.current_phase}

## Context
Verify the Dev implementation from phase {state.current_phase}.

## Your Tasks
1. Review the code changes made by Dev agent
2. Run unit tests and integration tests
3. Check for common bugs and edge cases
4. Verify functionality matches PRD requirements
5. Document any issues found

## Test Commands
- Unit tests: pytest tests/ -v
- Integration tests: python scripts/e2e_test.py

## Deliverables
Write your results to the result.md file with:
- Test results (pass/fail)
- Issues found (if any)
- Recommendations
"""

    dev_task_file = get_task_file(phase_id, AgentRole.DEV)
    qa_task_file = get_task_file(phase_id, AgentRole.QA)

    write_task(dev_task_file, dev_task_content)
    write_task(qa_task_file, qa_task_content)

    phase.tasks_assigned = [
        TaskAssignment(agent=AgentRole.DEV, task_file=str(dev_task_file), priority=1),
        TaskAssignment(agent=AgentRole.QA, task_file=str(qa_task_file), priority=2),
    ]

    phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.PENDING
    phase.agent_statuses[AgentRole.QA.value] = AgentStatus.PENDING
    _touch_phases(state)

    MetricsCollector.record_planning_rounds(phase_id, 1)

    from_action = state.next_action
    target = state.set_next_action("dispatch_dev", reason="lead_plan_completed")
    if target != "dispatch_dev":
        log_event(
            "invalid_transition_rejected",
            project_id=state.project_id,
            phase=state.current_phase,
            from_action=from_action,
            attempted_to="dispatch_dev",
            resolved_to=target,
        )

    return state


async def dispatch_dev_node(state: ProjectState) -> ProjectState:
    state.next_action = "dispatch_dev"
    log_event("dispatch_dev", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if phase:
        phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.RUNNING
        _touch_phases(state)

    from_action = state.next_action
    target = state.set_next_action("wait_dev", reason="dev_dispatched")
    if target != "wait_dev":
        log_event(
            "invalid_transition_rejected",
            project_id=state.project_id,
            phase=state.current_phase,
            from_action=from_action,
            attempted_to="wait_dev",
            resolved_to=target,
        )

    return state


async def wait_dev_node(state: ProjectState) -> ProjectState:
    state.next_action = "wait_dev"
    log_event("wait_dev", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if not phase:
        state.set_next_action("phase_fail", reason="phase_not_found_in_wait_dev")
        return state

    dev_status = phase.agent_statuses.get(AgentRole.DEV.value, AgentStatus.PENDING)

    if dev_status == AgentStatus.SUCCESS:
        state.artifacts.pop("wait_dev_cycles", None)
        _touch_artifacts(state)
        state.set_next_action("dispatch_qa", reason="dev_success")
    elif dev_status == AgentStatus.FAILED:
        state.artifacts.pop("wait_dev_cycles", None)
        _touch_artifacts(state)
        state.set_next_action("phase_fail", reason="dev_failed")
    else:
        cycles = int(state.artifacts.get("wait_dev_cycles", 0)) + 1
        state.artifacts["wait_dev_cycles"] = cycles
        _touch_artifacts(state)
        if cycles > settings.wait_node_max_cycles:
            state.set_next_action("phase_fail", reason="dev_wait_timeout")
        else:
            state.set_next_action("wait_dev", reason=f"dev_not_ready:{dev_status.value}")
    return state


async def dispatch_qa_node(state: ProjectState) -> ProjectState:
    state.next_action = "dispatch_qa"
    log_event("dispatch_qa", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if phase:
        phase.agent_statuses[AgentRole.QA.value] = AgentStatus.RUNNING
        _touch_phases(state)

    from_action = state.next_action
    target = state.set_next_action("wait_qa", reason="qa_dispatched")
    if target != "wait_qa":
        log_event(
            "invalid_transition_rejected",
            project_id=state.project_id,
            phase=state.current_phase,
            from_action=from_action,
            attempted_to="wait_qa",
            resolved_to=target,
        )

    return state


async def wait_qa_node(state: ProjectState) -> ProjectState:
    state.next_action = "wait_qa"
    log_event("wait_qa", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if not phase:
        state.set_next_action("phase_fail", reason="phase_not_found_in_wait_qa")
        return state

    qa_status = phase.agent_statuses.get(AgentRole.QA.value, AgentStatus.PENDING)

    if qa_status == AgentStatus.SUCCESS:
        state.artifacts.pop("wait_qa_cycles", None)
        _touch_artifacts(state)
        state.set_next_action("lead_integrate", reason="qa_success")
    elif qa_status == AgentStatus.FAILED:
        state.artifacts.pop("wait_qa_cycles", None)
        _touch_artifacts(state)
        state.set_next_action("phase_fail", reason="qa_failed")
    else:
        cycles = int(state.artifacts.get("wait_qa_cycles", 0)) + 1
        state.artifacts["wait_qa_cycles"] = cycles
        _touch_artifacts(state)
        if cycles > settings.wait_node_max_cycles:
            state.set_next_action("phase_fail", reason="qa_wait_timeout")
        else:
            state.set_next_action("wait_qa", reason=f"qa_not_ready:{qa_status.value}")
    return state


async def lead_integrate_node(state: ProjectState) -> ProjectState:
    state.next_action = "lead_integrate"
    log_event("lead_integrate", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if not phase:
        state.set_next_action("phase_fail", reason="phase_not_found_in_lead_integrate")
        return state

    gate_suite = _build_phase_gate_suite(state)
    invariant_report = _build_invariant_report(state)
    scorer = EnergyScorer()
    previous_energy = state.energy_history[-1] if state.energy_history else None
    current_energy = scorer.from_gate_suite(gate_suite, invariant_report)
    decision = DecisionPolicy().decide(previous_energy, current_energy)
    scorer.update_calibration(
        weighted_score=current_energy.weighted_score,
        succeeded=decision.decision == ConvergenceAction.ADVANCE,
    )

    phase.energy_vector = current_energy
    phase.convergence_decision = decision
    state.energy_history.append(current_energy)
    _touch_energy_history(state)
    _touch_phases(state)

    phase_id = f"phase_{state.current_phase:02d}"
    state.artifacts[f"{phase_id}_energy"] = current_energy.model_dump(mode="json")
    state.artifacts[f"{phase_id}_decision"] = decision.model_dump(mode="json")
    _touch_artifacts(state)

    if decision.decision == ConvergenceAction.ADVANCE:
        phase.status = "completed"
        phase.completed_at = datetime.now()
        _touch_phases(state)
        if phase.started_at:
            duration = (phase.completed_at - phase.started_at).total_seconds()
            MetricsCollector.record_workflow(phase_id, "completed", duration)
        state.set_next_action("phase_done", reason="integration_completed")
    elif decision.decision in {ConvergenceAction.RETRY, ConvergenceAction.DIAGNOSE}:
        phase.review_loops += 1
        _touch_phases(state)
        if phase.review_loops > settings.max_planner_reviewer_loops:
            phase.status = "failed"
            phase.completed_at = datetime.now()
            _touch_phases(state)
            state.set_next_action("phase_fail", reason="control_loop_limit_reached")
        else:
            if decision.decision == ConvergenceAction.RETRY:
                phase.repair_decision = _build_default_repair_decision(state)
                _touch_phases(state)
                state.set_next_action("rollback_phase", reason="control_decision:retry")
            else:
                state.set_next_action("diagnose_phase", reason="control_decision:diagnose")
    else:
        if decision.decision == ConvergenceAction.HALT:
            repair_decision = RepairPlanner().plan(current_energy)
            phase.repair_decision = repair_decision
            _touch_phases(state)
            state.artifacts[f"{phase.phase_id}_halt_repair_decision"] = repair_decision.model_dump(mode="json")
            _touch_artifacts(state)
            if repair_decision.rollback_target_layer.value in {"spec", "contract", "task"}:
                state.set_next_action("diagnose_phase", reason="control_decision:halt_with_repair_plan")
                return state

        phase.status = "failed"
        phase.completed_at = datetime.now()
        _touch_phases(state)
        state.set_next_action("phase_fail", reason=f"control_decision:{decision.decision.value}")

    return state


async def diagnose_phase_node(state: ProjectState) -> ProjectState:
    state.next_action = "diagnose_phase"
    log_event("diagnose_phase", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if not phase or not phase.energy_vector:
        state.set_next_action("phase_fail", reason="missing_energy_for_diagnosis")
        return state

    repair_decision = RepairPlanner().plan(phase.energy_vector)
    phase.repair_decision = repair_decision
    _touch_phases(state)
    state.artifacts[f"{phase.phase_id}_repair_decision"] = repair_decision.model_dump(mode="json")
    _touch_artifacts(state)
    state.set_next_action("rollback_phase", reason=f"diagnosed:{repair_decision.rollback_target_layer.value}")
    return state


async def rollback_phase_node(state: ProjectState) -> ProjectState:
    state.next_action = "rollback_phase"
    log_event("rollback_phase", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if not phase or not phase.repair_decision:
        state.set_next_action("phase_fail", reason="missing_repair_decision")
        return state

    manager = RollbackManager()
    execution = manager.execute(state, phase.repair_decision)
    phase.repair_execution = execution
    _touch_phases(state)
    _touch_artifacts(state)
    if execution.execution_status.value != "executed":
        state.set_next_action("phase_fail", reason="rollback_execution_failed")
        return state

    state.set_next_action(manager.next_action_for(phase.repair_decision), reason="rollback_completed")
    return state


async def phase_done_node(state: ProjectState) -> ProjectState:
    state.next_action = "phase_done"
    log_event("phase_done", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    if phase:
        phase.status = "done"
        _touch_phases(state)

    phase_id = f"phase_{state.current_phase:02d}"
    MetricsCollector.decrement_workflow_active(phase_id)

    state.is_completed = True

    return state


async def phase_fail_node(state: ProjectState) -> ProjectState:
    state.next_action = "phase_fail"
    log_event("phase_fail", phase=state.current_phase, project_id=state.project_id)

    phase = state.get_current_phase()
    phase_id = f"phase_{state.current_phase:02d}"

    if phase:
        phase.status = "failed"
        _touch_phases(state)
        if phase.started_at:
            duration = (datetime.now() - phase.started_at).total_seconds()
            MetricsCollector.record_workflow(phase_id, "failed", duration)

    MetricsCollector.decrement_workflow_active(phase_id)

    state.is_failed = True

    return state
