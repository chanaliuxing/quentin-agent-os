from app.models import (
    AgentRole,
    AgentStatus,
    PhaseState,
    ProjectState,
    RepairDecision,
    RollbackTargetLayer,
)
from app.rollback import RollbackManager


def build_state() -> ProjectState:
    state = ProjectState(project_id="project_alpha", prd_path="prd.md")
    phase = PhaseState(phase_id="phase_01", phase_number=1)
    phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.SUCCESS
    phase.agent_statuses[AgentRole.QA.value] = AgentStatus.SUCCESS
    state.phases.append(phase)
    return state


def test_rollback_manager_resets_phase_and_creates_checkpoint():
    state = build_state()
    decision = RepairDecision(
        run_id=state.project_id,
        phase_id="phase_01",
        failure_class="implementation_bug",
        rollback_target_layer=RollbackTargetLayer.IMPLEMENTATION,
        rollback_scope=["module_alpha"],
        affected_modules=["module_alpha"],
        required_agents=["dev", "qa"],
        repair_strategy="rerun implementation",
        confidence=0.8,
    )
    execution = RollbackManager().execute(state, decision)
    phase = state.get_current_phase()
    assert phase is not None
    assert execution.execution_status.value == "executed"
    assert phase.agent_statuses[AgentRole.DEV.value] == AgentStatus.PENDING
    assert "phase_01_checkpoint" in state.artifacts
    assert state.artifacts["phase_01_resolved_scope_modules"] == ["module_alpha"]
    assert state.artifacts["phase_01_rollback_scope"]["scope_source"] == "heuristic"
    assert state.artifacts["phase_01_rollback_scope"]["scope_confidence"] == 0.5
    assert any("scope_source=heuristic" == note for note in execution.notes)


def test_rollback_manager_routes_spec_repairs_to_lead_plan():
    decision = RepairDecision(
        run_id="run_01",
        phase_id="phase_01",
        failure_class="ownership_violation",
        rollback_target_layer=RollbackTargetLayer.SPEC,
        rollback_scope=["module_alpha"],
        affected_modules=["module_alpha"],
        required_agents=["lead", "planner"],
        repair_strategy="fix spec",
        confidence=0.9,
    )
    assert RollbackManager().next_action_for(decision) == "lead_plan"
