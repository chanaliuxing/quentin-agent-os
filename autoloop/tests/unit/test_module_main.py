import pytest

from app.module_main import (
    AcquisitionTrack,
    ExecutionStep,
    ModuleMainOrchestrator,
    StepResult,
    ToolCapability,
    decompose_task,
    recommend_next_investment,
    select_mcp_tool,
)
from app.module_main.core import ToolLearningRegistry


def test_decompose_task_infers_capabilities_from_text():
    steps = decompose_task("Automate desktop workflow. Review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_semicolon_separator():
    steps = decompose_task("Automate desktop workflow; Review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_comma_separator():
    steps = decompose_task("Automate desktop workflow, Review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_and_connector_separator():
    steps = decompose_task("Automate desktop workflow and review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_ampersand_connector_separator():
    steps = decompose_task("Automate desktop workflow & review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_does_not_split_embedded_ampersand_tokens():
    steps = decompose_task("Improve R&D workflow")

    assert len(steps) == 1
    assert steps[0].description == "Improve R&D workflow"


def test_decompose_task_does_not_split_embedded_ampersand_tokens_without_whitespace():
    steps = decompose_task("Audit M&A pipeline")

    assert len(steps) == 1
    assert steps[0].description == "Audit M&A pipeline"


def test_decompose_task_supports_arrow_connector_separator():
    steps = decompose_task("Automate desktop workflow -> review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_chinese_ji_connector_separator():
    steps = decompose_task("执行桌面自动化及审查法律合同")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_does_not_split_words_with_ambiguous_chinese_connector_chars():
    steps = decompose_task("实现并发控制")

    assert len(steps) == 1
    assert steps[0].required_capability == "self_programming"


def test_decompose_task_supports_chinese_connector_separator():
    steps = decompose_task("执行桌面自动化并且审查法律合同")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_chinese_comma_separator():
    steps = decompose_task("执行桌面自动化，审查法律合同")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_chinese_punctuation_separator():
    steps = decompose_task("执行桌面自动化。审查法律合同；生成新策略")

    assert len(steps) == 3
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"
    assert steps[2].required_capability == "self_programming"


def test_decompose_task_supports_question_and_exclamation_separator():
    steps = decompose_task("Automate desktop workflow? Review legal contract! Generate novel algorithm")

    assert len(steps) == 3
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"
    assert steps[2].required_capability == "self_programming"


def test_decompose_task_supports_windows_newline_separator():
    steps = decompose_task("Automate desktop workflow\r\nReview legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_supports_colon_separator():
    steps = decompose_task("Automate desktop workflow: Review legal contract")

    assert len(steps) == 2
    assert steps[0].required_capability == "desktop_automation"
    assert steps[1].required_capability == "legal_reasoning"


def test_decompose_task_routes_generation_steps_to_self_programming():
    steps = decompose_task("Generate novel algorithm")

    assert len(steps) == 1
    assert steps[0].required_capability == "self_programming"


def test_decompose_task_routes_programming_terms_to_self_programming():
    steps = decompose_task("Write a trading script")

    assert len(steps) == 1
    assert steps[0].required_capability == "self_programming"


def test_decompose_task_infers_chinese_capabilities():
    steps = decompose_task("研究市场趋势")

    assert len(steps) == 1
    assert steps[0].required_capability == "trading_ops"


def test_decompose_task_rejects_empty_input():
    with pytest.raises(ValueError, match="task must not be empty"):
        decompose_task("   ")


def test_decompose_task_defaults_unknown_english_text_to_general():
    steps = decompose_task("Summarize quarterly notes")

    assert len(steps) == 1
    assert steps[0].required_capability == "general"


def test_select_mcp_tool_prefers_highest_reliability_match():
    step = ExecutionStep(
        step_id="step_01",
        description="Automate desktop workflow",
        required_capability="desktop_automation",
    )
    tools = [
        ToolCapability(tool_name="tool_low", capabilities=["desktop_automation"], reliability=0.62),
        ToolCapability(tool_name="tool_high", capabilities=["desktop_automation"], reliability=0.95),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "tool_high"


def test_select_mcp_tool_normalizes_capability_labels():
    step = ExecutionStep(
        step_id="step_01",
        description="Automate desktop workflow",
        required_capability="desktop automation",
    )
    tools = [
        ToolCapability(tool_name="desktop_tool", capabilities=["Desktop-Automation"], reliability=0.9),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "desktop_tool"


def test_select_mcp_tool_breaks_reliability_ties_by_tool_name():
    step = ExecutionStep(
        step_id="step_01",
        description="Automate desktop workflow",
        required_capability="desktop_automation",
    )
    tools = [
        ToolCapability(tool_name="zeta_tool", capabilities=["desktop_automation"], reliability=0.8),
        ToolCapability(tool_name="alpha_tool", capabilities=["desktop_automation"], reliability=0.8),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "alpha_tool"


def test_select_mcp_tool_uses_general_capability_as_fallback():
    step = ExecutionStep(
        step_id="step_01",
        description="Automate desktop workflow",
        required_capability="desktop_automation",
    )
    tools = [
        ToolCapability(tool_name="desktop_tool", capabilities=["desktop_automation"], reliability=0.55),
        ToolCapability(tool_name="general_tool", capabilities=["general"], reliability=0.8),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "general_tool"


def test_select_mcp_tool_treats_empty_tool_capabilities_as_general():
    step = ExecutionStep(
        step_id="step_01",
        description="Draft response",
        required_capability="general",
    )
    tools = [
        ToolCapability(tool_name="blank_caps_tool", capabilities=[], reliability=0.75),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "blank_caps_tool"


def test_select_mcp_tool_treats_invalid_normalized_capabilities_as_general():
    step = ExecutionStep(
        step_id="step_01",
        description="Draft response",
        required_capability="general",
    )
    tools = [
        ToolCapability(tool_name="invalid_caps_tool", capabilities=["---"], reliability=0.75),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is not None
    assert selected.tool_name == "invalid_caps_tool"


def test_select_mcp_tool_skips_tools_for_self_programming_steps():
    step = ExecutionStep(
        step_id="step_01",
        description="Generate novel algorithm",
        required_capability="self_programming",
    )
    tools = [
        ToolCapability(tool_name="general_tool", capabilities=["general"], reliability=0.95),
        ToolCapability(tool_name="code_assistant", capabilities=["self_programming"], reliability=0.99),
    ]

    selected = select_mcp_tool(step=step, tools=tools, min_reliability=0.6)

    assert selected is None


def test_select_mcp_tool_rejects_invalid_min_reliability():
    step = ExecutionStep(
        step_id="step_01",
        description="Automate desktop workflow",
        required_capability="desktop_automation",
    )

    with pytest.raises(ValueError, match="min_reliability"):
        select_mcp_tool(step=step, tools=[], min_reliability=1.5)


def test_tool_learning_registry_rejects_non_alphanumeric_tool_name():
    registry = ToolLearningRegistry()
    with pytest.raises(ValueError, match="alphanumeric"):
        registry.register(ToolCapability(tool_name="---", capabilities=["general"], reliability=0.8))


def test_recommend_next_investment_tracks_failure_patterns():
    results = [
        StepResult(
            step_id="step_01",
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="builder",
            success=False,
            output="failed",
        ),
        StepResult(
            step_id="step_02",
            track=AcquisitionTrack.MCP_TOOL,
            executor="tool",
            success=True,
            output="ok",
        ),
    ]

    investment = recommend_next_investment(results)

    assert investment == "self_programming_engine"


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_self_programming_when_tool_fails():
    async def tool_executor(step, tool):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=False,
            output="tool-failed",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="sp_engine",
            success=True,
            output="sp-recovered",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.9)],
    )

    assert result.step_results[0].track == AcquisitionTrack.SELF_PROGRAMMING
    assert result.step_results[0].success is True


@pytest.mark.asyncio
async def test_orchestrator_returns_failed_step_when_self_programming_raises():
    async def tool_executor(step, tool):
        raise RuntimeError("tool down")

    async def self_programming_executor(step):
        raise RuntimeError("sp down")

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.9)],
    )

    assert len(result.step_results) == 1
    assert result.step_results[0].track == AcquisitionTrack.SELF_PROGRAMMING
    assert result.step_results[0].success is False
    assert result.step_results[0].step_id == "step_01"


@pytest.mark.asyncio
async def test_orchestrator_normalizes_tool_result_metadata():
    async def tool_executor(step, tool):
        return StepResult(
            step_id="unexpected_step",
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="tool_executor_name",
            success=True,
            output="ok",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="sp_engine",
            success=True,
            output="sp-ok",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run(
        "Automate desktop workflow",
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.9)],
    )

    assert len(result.step_results) == 1
    assert result.step_results[0].step_id == "step_01"
    assert result.step_results[0].track == AcquisitionTrack.MCP_TOOL
    assert result.step_results[0].success is True


@pytest.mark.asyncio
async def test_orchestrator_run_with_registry_uses_registered_tools():
    async def tool_executor(step, tool):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=True,
            output="ok",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="sp_engine",
            success=True,
            output="ok",
        )

    registry = ToolLearningRegistry(
        [ToolCapability(tool_name="desktop mcp", capabilities=["Desktop-Automation"], reliability=0.9)]
    )
    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    result = await orchestrator.run_with_registry("Automate desktop workflow", registry)

    assert len(result.step_results) == 1
    assert result.step_results[0].track == AcquisitionTrack.MCP_TOOL
    assert result.step_results[0].executor == "desktop_mcp"


@pytest.mark.asyncio
async def test_orchestrator_run_with_registry_rejects_invalid_registry_type():
    async def tool_executor(step, tool):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=True,
            output="ok",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="sp_engine",
            success=True,
            output="ok",
        )

    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
    )

    with pytest.raises(TypeError, match="ToolLearningRegistry"):
        await orchestrator.run_with_registry("Automate desktop workflow", registry=object())  # type: ignore[arg-type]


def test_orchestrator_rejects_invalid_min_tool_reliability():
    async def tool_executor(step, tool):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.MCP_TOOL,
            executor=tool.tool_name,
            success=True,
            output="ok",
        )

    async def self_programming_executor(step):
        return StepResult(
            step_id=step.step_id,
            track=AcquisitionTrack.SELF_PROGRAMMING,
            executor="sp_engine",
            success=True,
            output="ok",
        )

    with pytest.raises(ValueError, match="min_tool_reliability"):
        ModuleMainOrchestrator(
            tool_executor=tool_executor,
            self_programming_executor=self_programming_executor,
            min_tool_reliability=1.2,
        )
