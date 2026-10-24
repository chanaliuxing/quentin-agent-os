import pytest

from app.graph.nodes import diagnose_phase_node, lead_integrate_node, rollback_phase_node
from app.models import AgentRole, AgentStatus, EnergyVector, PhaseState, ProjectState, TestResult as PhaseTestResult


def build_state() -> ProjectState:
    state = ProjectState(project_id="project_alpha", prd_path="prd.md")
    phase = PhaseState(phase_id="phase_01", phase_number=1)
    phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.SUCCESS
    phase.agent_statuses[AgentRole.QA.value] = AgentStatus.SUCCESS
    state.phases.append(phase)
    return state


@pytest.mark.asyncio
async def test_lead_integrate_advances_on_clean_energy():
    state = build_state()

    result = await lead_integrate_node(state)

    phase = result.get_current_phase()
    assert result.next_action == "phase_done"
    assert phase is not None
    assert phase.convergence_decision is not None
    assert phase.convergence_decision.decision.value == "advance"
    assert len(result.energy_history) == 1


@pytest.mark.asyncio
async def test_lead_integrate_replans_on_warning_energy():
    state = build_state()
    phase = state.get_current_phase()
    assert phase is not None
    phase.test_results.append(PhaseTestResult(test_name="integration_guard", status="warn"))

    result = await lead_integrate_node(state)

    phase = result.get_current_phase()
    assert result.next_action == "rollback_phase"
    assert phase is not None
    assert phase.review_loops == 1
    assert phase.convergence_decision is not None
    assert phase.convergence_decision.decision.value == "retry"
    assert phase.repair_decision is not None


@pytest.mark.asyncio
async def test_lead_integrate_fails_on_hard_fail_energy():
    state = build_state()
    phase = state.get_current_phase()
    assert phase is not None
    phase.test_results.append(PhaseTestResult(test_name="integration_guard", status="failed"))

    result = await lead_integrate_node(state)

    phase = result.get_current_phase()
    assert result.next_action == "phase_fail"
    assert phase is not None
    assert phase.convergence_decision is not None
    assert phase.convergence_decision.decision.value == "halt"


@pytest.mark.asyncio
async def test_lead_integrate_routes_repairable_halt_to_diagnose():
    state = build_state()
    phase = state.get_current_phase()
    assert phase is not None
    phase.test_results.append(PhaseTestResult(test_name="ownership_guard", status="failed"))

    result = await lead_integrate_node(state)

    phase = result.get_current_phase()
    assert phase is not None
    assert phase.convergence_decision is not None
    assert phase.convergence_decision.decision.value == "halt"
    assert phase.repair_decision is not None
    assert phase.repair_decision.rollback_target_layer.value == "spec"
    assert result.next_action == "diagnose_phase"


@pytest.mark.asyncio
async def test_diagnose_phase_creates_repair_decision():
    state = build_state()
    phase = state.get_current_phase()
    assert phase is not None
    phase.test_results.append(PhaseTestResult(test_name="schema_contract", status="warn"))
    state.energy_history.append(
        EnergyVector(
            energy_id="energy_prev",
            run_id=state.project_id,
            phase_id="phase_01",
            module_id="phase_01",
            weighted_score=0.95,
        )
    )

    integrated = await lead_integrate_node(state)
    phase = integrated.get_current_phase()
    assert phase is not None
    assert integrated.next_action == "diagnose_phase"

    diagnosed = await diagnose_phase_node(integrated)
    phase = diagnosed.get_current_phase()
    assert phase is not None
    assert diagnosed.next_action == "rollback_phase"
    assert phase.repair_decision is not None


@pytest.mark.asyncio
async def test_rollback_phase_routes_implementation_repairs_to_dispatch_dev():
    state = build_state()
    phase = state.get_current_phase()
    assert phase is not None
    phase.test_results.append(PhaseTestResult(test_name="integration_guard", status="warn"))

    integrated = await lead_integrate_node(state)
    rolled = await rollback_phase_node(integrated)
    phase = rolled.get_current_phase()
    assert phase is not None
    assert rolled.next_action == "dispatch_dev"
    assert phase.repair_execution is not None
