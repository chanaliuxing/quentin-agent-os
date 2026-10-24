import pytest
from pydantic import ValidationError

from app.models import (
    FileOwnershipRule,
    GatePolicy,
    InterfaceSpec,
    IoRef,
    ModuleSpec,
    ProjectSpec,
    WorkflowTopology,
)


def build_valid_spec(**overrides) -> ProjectSpec:
    payload = {
        "project_id": "project_alpha",
        "contract_version": "1.0",
        "modules": [
            ModuleSpec(
                module_id="planner",
                summary="planner module",
                depends_on=[],
                inputs=[IoRef(name="prd", schema_ref="schemas/prd.json")],
                outputs=[IoRef(name="plan", schema_ref="schemas/plan.json")],
                acceptance_criteria=["plan generated"],
            ),
            ModuleSpec(
                module_id="executor",
                summary="executor module",
                depends_on=["planner"],
                inputs=[IoRef(name="plan", schema_ref="schemas/plan.json")],
                outputs=[IoRef(name="result", schema_ref="schemas/result.json")],
                acceptance_criteria=["result produced"],
            ),
        ],
        "interfaces": [
            InterfaceSpec(
                interface_id="planner_to_executor",
                producer_module="planner",
                consumer_modules=["executor"],
                schema_ref="schemas/plan.json",
            )
        ],
        "ownership": [
            FileOwnershipRule(
                path_glob="app/planner/**",
                owner_role="planner",
                module_id="planner",
            )
        ],
        "gate_policy": GatePolicy(
            phase_gates=["spec_valid"],
            module_gates=["tests_pass"],
            score_threshold=0.8,
        ),
        "workflow_topology": WorkflowTopology(nodes=["planner", "executor"], edges=[]),
    }
    payload.update(overrides)
    return ProjectSpec.model_validate(payload)


def test_project_spec_rejects_duplicate_module_ids():
    with pytest.raises(ValidationError):
        build_valid_spec(
            modules=[
                ModuleSpec(
                    module_id="planner",
                    summary="planner module",
                    depends_on=[],
                    inputs=[],
                    outputs=[],
                    acceptance_criteria=[],
                ),
                ModuleSpec(
                    module_id="planner",
                    summary="duplicate planner module",
                    depends_on=[],
                    inputs=[],
                    outputs=[],
                    acceptance_criteria=[],
                ),
            ]
        )


def test_project_spec_rejects_missing_dependency_reference():
    with pytest.raises(ValidationError):
        build_valid_spec(
            modules=[
                ModuleSpec(
                    module_id="planner",
                    summary="planner module",
                    depends_on=["missing_module"],
                    inputs=[],
                    outputs=[],
                    acceptance_criteria=[],
                )
            ],
            interfaces=[],
            ownership=[],
            workflow_topology=WorkflowTopology(nodes=["planner"], edges=[]),
        )


def test_project_spec_rejects_unknown_interface_producer():
    with pytest.raises(ValidationError):
        build_valid_spec(
            interfaces=[
                InterfaceSpec(
                    interface_id="bad_interface",
                    producer_module="missing_module",
                    consumer_modules=["executor"],
                    schema_ref="schemas/plan.json",
                )
            ]
        )


def test_project_spec_accepts_valid_cross_references():
    spec = build_valid_spec()
    assert spec.project_id == "project_alpha"
    assert spec.modules[1].depends_on == ["planner"]
