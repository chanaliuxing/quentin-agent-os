from app.models import (
    FileOwnershipRule,
    GatePolicy,
    InterfaceSpec,
    IoRef,
    ModuleSpec,
    ProjectSpec,
    WorkflowTopology,
)
from app.sor import SorRepository


def build_project_spec() -> ProjectSpec:
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
        ownership=[
            FileOwnershipRule(
                path_glob="app/planner/**",
                owner_role="planner",
                module_id="planner",
            )
        ],
        gate_policy=GatePolicy(
            phase_gates=["spec_valid"],
            module_gates=["unit_pass"],
            score_threshold=0.8,
        ),
        workflow_topology=WorkflowTopology(nodes=["planner"], edges=[]),
    )


def test_sor_repository_round_trip(mock_settings):
    repository = SorRepository()
    spec = build_project_spec()

    saved_path = repository.save_project_spec("run_01", spec)
    loaded = repository.load_project_spec("run_01")

    assert saved_path.exists()
    assert loaded.project_id == spec.project_id
    assert loaded.modules[0].module_id == "planner"
