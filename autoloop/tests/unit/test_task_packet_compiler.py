from app.models import ModuleExecutionView
from app.tasking import PromptRenderer, TaskPacketCompiler, build_result_packet


def build_module_view() -> ModuleExecutionView:
    return ModuleExecutionView(
        module_id="planner",
        summary="planner module",
        depends_on=[],
        sor_refs=["project:project_alpha", "module:planner"],
        writable_paths=["app/planner/**"],
        input_artifact_refs=["input:prd"],
        expected_output_refs=["output:plan"],
        gate_expectations=["spec_valid", "unit_pass"],
        acceptance_criteria=["plan generated"],
    )


def test_task_packet_compiler_builds_packet():
    packet = TaskPacketCompiler().compile_for_agent(
        run_id="run_01",
        phase_id="phase_01",
        module_view=build_module_view(),
        agent="planner",
    )
    assert packet.task_id == "task_phase_01_planner_planner"
    assert packet.writable_paths == ["app/planner/**"]


def test_prompt_renderer_builds_markdown_and_prompt_packet():
    packet = TaskPacketCompiler().compile_for_agent(
        run_id="run_01",
        phase_id="phase_01",
        module_view=build_module_view(),
        agent="planner",
    )
    renderer = PromptRenderer()
    markdown = renderer.render_markdown(packet)
    prompt_packet = renderer.build_prompt_packet(packet)

    assert "## Writable Scope" in markdown
    assert prompt_packet.rendered_task_markdown == markdown
    assert prompt_packet.prompt_id == f"prompt_{packet.task_id}"


def test_result_packet_builder_preserves_task_identity():
    task_packet = TaskPacketCompiler().compile_for_agent(
        run_id="run_01",
        phase_id="phase_01",
        module_view=build_module_view(),
        agent="planner",
    )
    result_packet = build_result_packet(
        task_packet=task_packet,
        produced_artifact_ids=["artifact_plan_01"],
        contract_payload={"status": "success"},
        claimed_file_changes=["app/planner/main.py"],
    )
    assert result_packet.task_id == task_packet.task_id
    assert result_packet.run_id == task_packet.run_id
