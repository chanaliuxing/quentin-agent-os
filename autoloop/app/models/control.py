from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.gates import GateResult


class OverlapRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EnergyAction(str, Enum):
    ADVANCE = "advance"
    RETRY_MODULE = "retry_module"
    DIAGNOSE = "diagnose"
    ROLLBACK_PHASE = "rollback_phase"
    HALT = "halt"


class ConvergenceAction(str, Enum):
    ADVANCE = "advance"
    RETRY = "retry"
    DIAGNOSE = "diagnose"
    ROLLBACK = "rollback"
    HALT = "halt"


class RollbackTargetLayer(str, Enum):
    IMPLEMENTATION = "implementation"
    TASK = "task"
    CONTRACT = "contract"
    SPEC = "spec"


class RepairExecutionStatus(str, Enum):
    PLANNED = "planned"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EnergyVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    energy_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    schema_valid: bool = True
    build_valid: bool = True
    unit_valid: bool = True
    integration_valid: bool = True
    regression_valid: bool = True
    sor_invariants_valid: bool = True
    ownership_valid: bool = True
    provenance_complete: bool = True
    overlap_risk: OverlapRisk = OverlapRisk.NONE
    unresolved_failures: int = Field(default=0, ge=0)
    weighted_score: float = Field(ge=0.0, le=1.0)
    hard_fail: bool = False
    failing_invariants: list[str] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
    blame_candidates: list[str] = Field(default_factory=list)
    recommended_action: EnergyAction = EnergyAction.ADVANCE

    @model_validator(mode="after")
    def validate_hard_fail(self) -> "EnergyVector":
        if self.hard_fail and not self.failing_invariants:
            raise ValueError("hard_fail requires at least one failing invariant")
        return self


class ConvergenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    decision: ConvergenceAction
    hard_fail: bool = False
    failing_invariants: list[str] = Field(default_factory=list)
    blame_candidates: list[str] = Field(default_factory=list)
    energy: EnergyVector

    @model_validator(mode="after")
    def validate_failure_alignment(self) -> "ConvergenceDecision":
        if self.hard_fail and not self.failing_invariants:
            raise ValueError("hard_fail decisions require failing invariants")
        return self


class RepairDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    failure_class: str = Field(min_length=1)
    rollback_target_layer: RollbackTargetLayer
    rollback_scope: list[str] = Field(default_factory=list)
    affected_modules: list[str] = Field(default_factory=list)
    required_agents: list[str] = Field(default_factory=list)
    repair_strategy: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    scope_source: str = Field(default="heuristic", min_length=1)
    scope_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RepairExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    decision: RepairDecision
    execution_status: RepairExecutionStatus
    touched_modules: list[str] = Field(default_factory=list)
    generated_task_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
