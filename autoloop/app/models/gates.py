from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_name: str = Field(min_length=1)
    status: GateStatus
    hard_fail: bool = False
    score: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    message: str | None = None

    @model_validator(mode="after")
    def validate_hard_fail(self) -> "GateResult":
        if self.hard_fail and self.status != GateStatus.FAIL:
            raise ValueError("hard_fail gate results must use fail status")
        return self


class GateSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    results: list[GateResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_gate_names(self) -> "GateSuiteResult":
        gate_names = [result.gate_name for result in self.results]
        if len(gate_names) != len(set(gate_names)):
            raise ValueError("gate names must be unique within a gate suite")
        return self

