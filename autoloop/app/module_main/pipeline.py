from __future__ import annotations

import asyncio
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from .artifacts import normalize_phase_id, validate_phase_result_artifact, write_phase_result_artifact
from .core import (
    AcquisitionTrack,
    ExecutionStep,
    ModuleMainOrchestrator,
    StepResult,
    ToolCapability,
    ToolLearningRegistry,
    ToolExecutor,
    SelfProgrammingExecutor,
)

ArtifactRoot = str | PathLike[str] | Path


def _resolve_artifact_root(artifact_root: ArtifactRoot | None) -> Path:
    if artifact_root is None:
        return Path(__file__).resolve().parent / "artifacts"
    if isinstance(artifact_root, bool):
        raise TypeError("artifact_root must be a path-like value")
    if isinstance(artifact_root, (str, PathLike, Path)):
        return Path(artifact_root)
    raise TypeError("artifact_root must be a path-like value")


def _default_tools() -> list[ToolCapability]:
    return [
        ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.92),
        ToolCapability(tool_name="legal_mcp", capabilities=["legal_reasoning"], reliability=0.9),
        ToolCapability(tool_name="research_mcp", capabilities=["research"], reliability=0.88),
        ToolCapability(tool_name="trading_mcp", capabilities=["trading_ops"], reliability=0.87),
        ToolCapability(tool_name="general_mcp", capabilities=["general"], reliability=0.8),
    ]


async def _default_tool_executor(step: ExecutionStep, tool: ToolCapability) -> StepResult:
    return StepResult(
        step_id=step.step_id,
        track=AcquisitionTrack.MCP_TOOL,
        executor=tool.tool_name,
        success=True,
        output=f"tool:{tool.tool_name}",
    )


async def _default_self_programming_executor(step: ExecutionStep) -> StepResult:
    return StepResult(
        step_id=step.step_id,
        track=AcquisitionTrack.SELF_PROGRAMMING,
        executor="self_programming_engine",
        success=True,
        output="generated",
    )


def _coerce_tools(tools: list[ToolCapability] | None) -> list[ToolCapability] | None:
    if tools is None:
        return None
    normalized_tools: list[ToolCapability] = []
    for tool in tools:
        if isinstance(tool, ToolCapability):
            normalized_tools.append(tool)
            continue
        if isinstance(tool, Mapping):
            normalized_tools.append(ToolCapability.model_validate(dict(tool)))
            continue
        raise TypeError("tools must contain ToolCapability instances or mapping payloads")
    return normalized_tools


async def run_phase_01_module_main(
    *,
    task: str,
    tools: list[ToolCapability] | None = None,
    tool_registry: ToolLearningRegistry | None = None,
    tool_executor: ToolExecutor | None = None,
    self_programming_executor: SelfProgrammingExecutor | None = None,
    min_tool_reliability: float = 0.6,
    artifact_root: ArtifactRoot | None = None,
    phase_id: str = "phase_01",
    rollback_on_failure: bool = True,
) -> Path:
    return await run_module_main_phase(
        task=task,
        tools=tools,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        self_programming_executor=self_programming_executor,
        min_tool_reliability=min_tool_reliability,
        artifact_root=artifact_root,
        phase_id=phase_id,
        rollback_on_failure=rollback_on_failure,
    )


async def run_module_main_phase(
    *,
    task: str,
    tools: list[ToolCapability] | None = None,
    tool_registry: ToolLearningRegistry | None = None,
    tool_executor: ToolExecutor | None = None,
    self_programming_executor: SelfProgrammingExecutor | None = None,
    min_tool_reliability: float = 0.6,
    artifact_root: ArtifactRoot | None = None,
    phase_id: str,
    rollback_on_failure: bool = True,
) -> Path:
    root = _resolve_artifact_root(artifact_root)
    normalized_phase_id = normalize_phase_id(phase_id)
    artifact_path = root / f"{normalized_phase_id}_result.json"
    artifact_existed_before_run = artifact_path.exists()
    preexisting_artifact_bytes: bytes | None = None
    if artifact_existed_before_run:
        preexisting_artifact_bytes = await asyncio.to_thread(artifact_path.read_bytes)
    if tool_registry is not None and tools is not None:
        raise ValueError("tools and tool_registry are mutually exclusive")
    if tool_registry is not None and not isinstance(tool_registry, ToolLearningRegistry):
        raise TypeError("tool_registry must be a ToolLearningRegistry instance")
    normalized_tools = _coerce_tools(tools)
    orchestrator = ModuleMainOrchestrator(
        tool_executor=tool_executor or _default_tool_executor,
        self_programming_executor=self_programming_executor or _default_self_programming_executor,
        min_tool_reliability=min_tool_reliability,
    )
    try:
        if tool_registry is not None:
            result = await orchestrator.run_with_registry(task=task, registry=tool_registry)
        elif normalized_tools is not None:
            result = await orchestrator.run(task=task, tools=normalized_tools)
        else:
            result = await orchestrator.run(task=task, tools=_default_tools())
        artifact = await write_phase_result_artifact(
            phase_id=normalized_phase_id,
            module_result=result,
            artifact_root=root,
        )
        await validate_phase_result_artifact(
            artifact,
            required_phase_id=normalized_phase_id,
            required_module_name="module_main",
        )
        return artifact
    except Exception:
        if rollback_on_failure:
            if artifact_existed_before_run and preexisting_artifact_bytes is not None:
                await asyncio.to_thread(artifact_path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(artifact_path.write_bytes, preexisting_artifact_bytes)
            elif artifact_path.exists():
                await asyncio.to_thread(artifact_path.unlink)
        raise
