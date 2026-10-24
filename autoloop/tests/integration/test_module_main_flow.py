import json
import pytest

from app.module_main import (
    AcquisitionTrack,
    ModuleMainOrchestrator,
    StepResult,
    ToolCapability,
    run_module_main_phase,
    run_phase_01_module_main,
    write_phase_result_artifact,
)


@pytest.mark.asyncio
async def test_module_main_routes_mcp_first_and_falls_back_to_self_programming():
    tool_calls: list[str] = []
    self_programming_calls: list[str] = []

    async def tool_executor(step, tool):
        tool_calls.append(f"{step.step_id}:{tool.tool_name}")
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=True,
            output=f"tool:{tool.tool_name}",
        )

    async def self_programming_executor(step):
        self_programming_calls.append(step.step_id)
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="self_programming_engine",
            success=True,
            output="generated",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow. Generate novel algorithm",
        tools=[
            ToolCapability(
                tool_name="desktop_mcp",
                capabilities=["desktop_automation"],
                reliability=0.9,
            )
        ],
    )

    assert len(result.steps) == 2
    assert result.step_results[0].track == AcquisitionTrack.MCP_TOOL
    assert result.step_results[1].track == AcquisitionTrack.SELF_PROGRAMMING
    assert tool_calls == ["step_01:desktop_mcp"]
    assert self_programming_calls == ["step_02"]
    assert result.next_investment_area == "mcp_coverage_expansion"


@pytest.mark.asyncio
async def test_module_main_recovers_with_self_programming_when_tool_executor_raises():
    async def tool_executor(step, tool):
        raise RuntimeError(f"tool unavailable: {tool.tool_name}")

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="self_programming_engine",
            success=True,
            output="generated-fallback",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[
            ToolCapability(
                tool_name="desktop_mcp",
                capabilities=["desktop_automation"],
                reliability=0.9,
            )
        ],
    )

    assert len(result.step_results) == 1
    assert result.step_results[0].track == AcquisitionTrack.SELF_PROGRAMMING
    assert result.step_results[0].success is True


@pytest.mark.asyncio
async def test_module_main_marks_step_failed_when_all_executors_raise():
    async def tool_executor(step, tool):
        raise RuntimeError(f"tool unavailable: {tool.tool_name}")

    async def self_programming_executor(step):
        raise RuntimeError("self programming unavailable")

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[
            ToolCapability(
                tool_name="desktop_mcp",
                capabilities=["desktop_automation"],
                reliability=0.9,
            )
        ],
    )

    assert len(result.step_results) == 1
    assert result.step_results[0].track == AcquisitionTrack.SELF_PROGRAMMING
    assert result.step_results[0].success is False
    assert result.next_investment_area == "self_programming_engine"


@pytest.mark.asyncio
async def test_module_main_writes_phase_result_artifact(tmp_path):
    async def tool_executor(step, tool):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=True,
            output="tool-ok",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="self_programming_engine",
            success=True,
            output="sp-ok",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )
    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.95)],
    )
    artifact_path = await write_phase_result_artifact(
        phase_id="phase_01",
        module_result=result,
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    assert artifact_path.exists()
    assert artifact_path.name == "phase_01_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["summary"]["next_investment_area"].strip() != ""


@pytest.mark.asyncio
async def test_module_main_probe_phase_artifact_generation(tmp_path):
    artifact_path = await run_module_main_phase(
        task="Probe session policy agent spec",
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        phase_id="phase_probe_session_policy_agent_spec",
        rollback_on_failure=True,
    )

    assert artifact_path.name == "phase_probe_session_policy_agent_spec_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["phase_id"] == "phase_probe_session_policy_agent_spec"
    assert payload["module_name"] == "module_main"


@pytest.mark.asyncio
async def test_module_main_probe_window_phase_artifact_generation(tmp_path):
    artifact_path = await run_module_main_phase(
        task="Probe session policy window",
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        phase_id="phase_probe_session_policy_window",
        rollback_on_failure=True,
    )

    assert artifact_path.name == "phase_probe_session_policy_window_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["phase_id"] == "phase_probe_session_policy_window"
    assert payload["module_name"] == "module_main"


@pytest.mark.asyncio
async def test_run_module_main_phase_accepts_string_artifact_root(tmp_path):
    artifact_root = str(tmp_path / "app" / "module_main" / "artifacts")
    artifact_path = await run_module_main_phase(
        task="Probe session policy window",
        artifact_root=artifact_root,
        phase_id="phase_probe_session_policy_window",
        rollback_on_failure=True,
    )

    assert artifact_path == tmp_path / "app" / "module_main" / "artifacts" / "phase_probe_session_policy_window_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["phase_id"] == "phase_probe_session_policy_window"
