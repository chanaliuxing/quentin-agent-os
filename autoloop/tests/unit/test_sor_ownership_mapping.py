from app.models import (
    FileOwnershipRule,
    GatePolicy,
    InterfaceSpec,
    IoRef,
    ModuleSpec,
    ProjectSpec,
    WorkflowTopology,
)
from app.sor.ownership import module_ids_from_scope_tokens


def build_spec() -> ProjectSpec:
    return ProjectSpec(
        project_id="project_alpha",
        contract_version="1.0",
        modules=[
            ModuleSpec(
                module_id="planner",
                summary="planner",
                depends_on=[],
                inputs=[IoRef(name="prd", schema_ref="schemas/prd.json")],
                outputs=[IoRef(name="plan", schema_ref="schemas/plan.json")],
                acceptance_criteria=["ok"],
            ),
            ModuleSpec(
                module_id="executor",
                summary="executor",
                depends_on=["planner"],
                inputs=[IoRef(name="plan", schema_ref="schemas/plan.json")],
                outputs=[IoRef(name="result", schema_ref="schemas/result.json")],
                acceptance_criteria=["ok"],
            ),
        ],
        interfaces=[
            InterfaceSpec(
                interface_id="planner_to_executor",
                producer_module="planner",
                consumer_modules=["executor"],
                schema_ref="schemas/plan.json",
            )
        ],
        ownership=[
            FileOwnershipRule(path_glob="app/planner/**", owner_role="planner", module_id="planner"),
            FileOwnershipRule(path_glob="app/executor/**", owner_role="executor", module_id="executor"),
        ],
        gate_policy=GatePolicy(phase_gates=["spec"], module_gates=["unit"], score_threshold=0.8),
        workflow_topology=WorkflowTopology(nodes=["planner", "executor"], edges=[]),
    )


def test_module_ids_from_scope_tokens_resolves_interface_and_paths():
    resolved = module_ids_from_scope_tokens(
        spec=build_spec(),
        scope_tokens=["interface:planner_to_executor", "app/executor/main.py"],
    )
    assert resolved == ["planner", "executor"]
