import pytest
from datetime import datetime
from app.models import (
    AcceptanceStatus,
    AgentRole,
    AgentStatus,
    ExecutionStatus,
    OrchestrationStatus,
    ProjectState,
    PhaseState,
    TaskAssignment,
    AgentResult,
)


def test_agent_role_enum():
    assert AgentRole.LEAD.value == "lead"
    assert AgentRole.DEV.value == "dev"
    assert AgentRole.QA.value == "qa"


def test_agent_status_enum():
    assert AgentStatus.PENDING.value == "pending"
    assert AgentStatus.SUCCESS.value == "success"
    assert AgentStatus.FAILED.value == "failed"


def test_semantic_status_enums():
    assert OrchestrationStatus.PENDING.value == "pending"
    assert ExecutionStatus.NOT_STARTED.value == "not_started"
    assert AcceptanceStatus.NOT_EVALUATED.value == "not_evaluated"


def test_task_assignment_creation():
    task = TaskAssignment(agent=AgentRole.DEV, task_file="/path/to/task.md", priority=1)
    assert task.agent == AgentRole.DEV
    assert task.task_file == "/path/to/task.md"
    assert task.priority == 1
    assert isinstance(task.created_at, datetime)


def test_agent_result_creation():
    result = AgentResult(
        agent=AgentRole.DEV, status=AgentStatus.SUCCESS, result_file="/path/to/result.md"
    )
    assert result.agent == AgentRole.DEV
    assert result.status == AgentStatus.SUCCESS
    assert result.duration_seconds == 0.0


def test_phase_state_creation():
    phase = PhaseState(phase_id="phase_01", phase_number=1)
    assert phase.phase_id == "phase_01"
    assert phase.phase_number == 1
    assert phase.status == "pending"
    assert phase.orchestration_status == OrchestrationStatus.PENDING
    assert phase.execution_status == ExecutionStatus.NOT_STARTED
    assert phase.acceptance_status == AcceptanceStatus.NOT_EVALUATED
    assert phase.review_loops == 0


def test_project_state_creation():
    project = ProjectState(project_id="test-project", prd_path="/path/to/prd.md")
    assert project.project_id == "test-project"
    assert project.current_phase == 1
    assert project.is_completed is False
    assert project.is_failed is False


def test_project_state_add_phase():
    project = ProjectState(project_id="test-project", prd_path="/path/to/prd.md")
    phase = project.add_phase("phase_01")
    assert len(project.phases) == 1
    assert phase.phase_id == "phase_01"
    assert phase.phase_number == 1


def test_project_state_get_current_phase():
    project = ProjectState(project_id="test-project", prd_path="/path/to/prd.md")
    assert project.get_current_phase() is None

    phase = project.add_phase("phase_01")
    current = project.get_current_phase()
    assert current is not None
    assert current.phase_id == "phase_01"
