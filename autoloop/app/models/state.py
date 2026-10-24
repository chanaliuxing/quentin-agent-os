from __future__ import annotations

from enum import Enum
from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field
from .control import ConvergenceDecision, EnergyVector, RepairDecision, RepairExecutionResult


class AgentRole(str, Enum):
    LEAD = "lead"
    PLANNER = "planner"
    REVIEWER = "reviewer"
    DEV = "dev"
    QA = "qa"
    INTEGRATOR = "integrator"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class OrchestrationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DIFF_CREATED = "diff_created"
    TESTS_FAILED = "tests_failed"
    TESTS_PASSED = "tests_passed"
    ROLLED_BACK = "rolled_back"


class AcceptanceStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    REJECTED = "rejected"
    CONDITIONALLY_PASSED = "conditionally_passed"
    PASSED = "passed"


class TaskAssignment(BaseModel):
    agent: AgentRole
    module_name: str | None = None
    task_file: str
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class AgentResult(BaseModel):
    agent: AgentRole
    module_name: str | None = None
    status: AgentStatus
    result_file: str
    commit_sha: str | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None
    completed_at: datetime = Field(default_factory=datetime.now)


class GitOverlap(BaseModel):
    file_path: str
    agents: list[AgentRole]
    commits: list[str]
    risk_level: str = "medium"


class TestResult(BaseModel):
    test_name: str
    status: str
    duration_seconds: float = 0.0
    error_message: str | None = None


class PhaseState(BaseModel):
    phase_id: str
    phase_number: int
    status: str = "pending"
    orchestration_status: OrchestrationStatus = OrchestrationStatus.PENDING
    execution_status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    acceptance_status: AcceptanceStatus = AcceptanceStatus.NOT_EVALUATED
    review_loops: int = 0
    tasks_assigned: list[TaskAssignment] = Field(default_factory=list)
    agent_statuses: dict[str, AgentStatus] = Field(default_factory=dict)
    agent_results: list[AgentResult] = Field(default_factory=list)
    git_overlaps: list[GitOverlap] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    energy_vector: EnergyVector | None = None
    convergence_decision: ConvergenceDecision | None = None
    repair_decision: RepairDecision | None = None
    repair_execution: RepairExecutionResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProjectState(BaseModel):
    project_id: str
    prd_path: str
    current_phase: int = 1
    phases: list[PhaseState] = Field(default_factory=list)
    next_action: str = "lead_plan"
    artifacts: dict[str, Any] = Field(default_factory=dict)
    energy_history: list[EnergyVector] = Field(default_factory=list)
    transition_history: list[TransitionEvent] = Field(default_factory=list)
    is_completed: bool = False
    is_failed: bool = False
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_current_phase(self) -> PhaseState | None:
        for phase in self.phases:
            if phase.phase_number == self.current_phase:
                return phase
        return None

    def add_phase(self, phase_id: str) -> PhaseState:
        phase = PhaseState(phase_id=phase_id, phase_number=self.current_phase)
        self.phases.append(phase)
        return phase

    def can_transition(self, from_action: str, to_action: str) -> bool:
        allowed = TRANSITION_MATRIX.get(from_action, set())
        return to_action in allowed

    def record_transition(
        self,
        *,
        from_action: str,
        to_action: str,
        reason: str,
        accepted: bool,
    ) -> None:
        self.transition_history.append(
            TransitionEvent(
                from_action=from_action,
                to_action=to_action,
                reason=reason,
                accepted=accepted,
                phase=self.current_phase,
            )
        )
        self.updated_at = datetime.now()

    def set_next_action(
        self,
        to_action: str,
        *,
        reason: str,
        reject_fallback: str = "phase_fail",
    ) -> str:
        from_action = self.next_action
        accepted = self.can_transition(from_action, to_action)
        if accepted:
            self.next_action = to_action
            self.record_transition(
                from_action=from_action,
                to_action=to_action,
                reason=reason,
                accepted=True,
            )
            return to_action

        fallback_allowed = self.can_transition(from_action, reject_fallback)
        fallback_target = reject_fallback if fallback_allowed else from_action
        self.next_action = fallback_target
        self.record_transition(
            from_action=from_action,
            to_action=to_action,
            reason=reason,
            accepted=False,
        )
        return fallback_target

    def replay_transitions(self) -> str:
        action = "lead_plan"
        for event in self.transition_history:
            if not self.can_transition(action, event.to_action):
                raise ValueError(
                    f"Invalid replay transition: {action} -> {event.to_action}"
                )
            if event.accepted:
                action = event.to_action
        return action


class TransitionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    timestamp: datetime = Field(default_factory=datetime.now)
    from_action: str
    to_action: str
    reason: str
    accepted: bool
    phase: int


TRANSITION_MATRIX: dict[str, set[str]] = {
    "lead_plan": {"dispatch_dev", "phase_fail"},
    "dispatch_dev": {"wait_dev", "phase_fail"},
    "wait_dev": {"wait_dev", "dispatch_qa", "phase_fail"},
    "dispatch_qa": {"wait_qa", "phase_fail"},
    "wait_qa": {"wait_qa", "lead_integrate", "phase_fail"},
    "lead_integrate": {"phase_done", "phase_fail", "lead_plan", "diagnose_phase", "rollback_phase"},
    "diagnose_phase": {"rollback_phase", "phase_fail"},
    "rollback_phase": {"dispatch_dev", "lead_plan", "phase_fail"},
    "phase_done": set(),
    "phase_fail": set(),
}
