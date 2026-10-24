from app.models import (
    FileOwnershipRule,
    GatePolicy,
    InterfaceSpec,
    IoRef,
    ModuleSpec,
    ProjectSpec,
    WorkflowTopology,
)
from app.sor import SorCompiler, SorRepository, SorValidator
from app.tasking import PromptRenderer, TaskPacketCompiler


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


def test_sor_to_task_packet_flow(mock_settings):
    repository = SorRepository()
    validator = SorValidator()
    compiler = SorCompiler()
    tasking = TaskPacketCompiler()
    renderer = PromptRenderer()

    spec = build_project_spec()
    repository.save_project_spec("run_01", spec)
    loaded = repository.load_project_spec("run_01")
    report = validator.validate(loaded)
    module_view = compiler.compile_module_view(loaded, "planner")
    task_packet = tasking.compile_for_agent(
        run_id="run_01",
        phase_id="phase_01",
        module_view=module_view,
        agent="planner",
    )
    markdown = renderer.render_markdown(task_packet)

    assert report.valid is True
    assert task_packet.module_id == "planner"
    assert "module:planner" in task_packet.sor_refs
    assert "`agent`: `planner`" in markdown
