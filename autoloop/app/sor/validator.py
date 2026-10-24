from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models import ProjectSpec


class InvariantViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    level: str = Field(min_length=1)
    message: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)


class InvariantReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    violations: list[InvariantViolation] = Field(default_factory=list)

    @property
    def failing_invariants(self) -> list[str]:
        return [violation.rule_id for violation in self.violations]


class SorValidator:
    def validate(self, spec: ProjectSpec) -> InvariantReport:
        violations: list[InvariantViolation] = []
        ownership_modules = {rule.module_id for rule in spec.ownership}
        topology_modules = set(spec.workflow_topology.nodes)

        for module in spec.modules:
            if module.module_id not in ownership_modules:
                violations.append(
                    InvariantViolation(
                        rule_id="module_has_owner",
                        level="error",
                        message=f"module {module.module_id} has no ownership rule",
                        subject_id=module.module_id,
                    )
                )
            if module.module_id not in topology_modules:
                violations.append(
                    InvariantViolation(
                        rule_id="module_in_topology",
                        level="error",
                        message=f"module {module.module_id} is absent from workflow topology",
                        subject_id=module.module_id,
                    )
                )

        if not spec.gate_policy.phase_gates:
            violations.append(
                InvariantViolation(
                    rule_id="phase_gates_declared",
                    level="error",
                    message="phase gates must not be empty",
                    subject_id=spec.project_id,
                )
            )
        if not spec.gate_policy.module_gates:
            violations.append(
                InvariantViolation(
                    rule_id="module_gates_declared",
                    level="error",
                    message="module gates must not be empty",
                    subject_id=spec.project_id,
                )
            )

        return InvariantReport(valid=not violations, violations=violations)
