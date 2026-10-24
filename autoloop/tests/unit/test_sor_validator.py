from app.models import (
    FileOwnershipRule,
    GatePolicy,
    InterfaceSpec,
    IoRef,
    ModuleSpec,
    ProjectSpec,
    WorkflowTopology,
)
from app.sor import SorValidator


def build_spec_with_optional_owner(include_owner: bool) -> ProjectSpec:
    ownership = []
    if include_owner:
        ownership.append(
            FileOwnershipRule(
                path_glob="app/planner/**",
                owner_role="planner",
                module_id="planner",
            )
        )
    return ProjectSpec(
        project_id="project_alpha",
        contract_version="1.0",
        modules=[
            ModuleSpec(
                module_id="planner",
                summary="planner module",
                depends_on=[],
                inputs=[IoRef(name="prd", schema_ref="schemas/prd.json")],
                outputs=[IoRef(name="plan", schema_ref="schemas/plan.json")],
                acceptance_criteria=["plan generated"],
            )
        ],
        interfaces=[
            InterfaceSpec(
                interface_id="planner_output",
                producer_module="planner",
                consumer_modules=[],
                schema_ref="schemas/plan.json",
            )
        ],
        ownership=ownership,
        gate_policy=GatePolicy(
            phase_gates=["spec_valid"],
            module_gates=["unit_pass"],
            score_threshold=0.8,
        ),
        workflow_topology=WorkflowTopology(nodes=["planner"], edges=[]),
    )


def test_sor_validator_passes_valid_spec():
    report = SorValidator().validate(build_spec_with_optional_owner(include_owner=True))
    assert report.valid is True
    assert report.violations == []


def test_sor_validator_detects_missing_owner():
    report = SorValidator().validate(build_spec_with_optional_owner(include_owner=False))
    assert report.valid is False
    assert "module_has_owner" in report.failing_invariants
