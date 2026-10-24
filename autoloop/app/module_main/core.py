from __future__ import annotations

from enum import Enum
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field


class AcquisitionTrack(str, Enum):
    MCP_TOOL = "mcp_tool"
    SELF_PROGRAMMING = "self_programming"


class ToolCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)


class ToolLearningRegistry:
    def __init__(self, tools: list[ToolCapability] | None = None) -> None:
        self._tools_by_name: dict[str, ToolCapability] = {}
        self._tool_observations: dict[str, tuple[int, int]] = {}
        if tools:
            self.register_many(tools)

    def register(self, tool: ToolCapability) -> ToolCapability:
        normalized_name = _normalize_tool_name(tool.tool_name)
        normalized_capability_set: set[str] = set()
        for item in tool.capabilities:
            normalized_capability = _normalize_capability(item)
            if normalized_capability:
                normalized_capability_set.add(normalized_capability)
        normalized_capabilities = sorted(normalized_capability_set)
        if not normalized_capabilities:
            normalized_capabilities = ["general"]

        normalized_tool = ToolCapability(
            tool_name=normalized_name,
            capabilities=normalized_capabilities,
            reliability=tool.reliability,
        )

        existing = self._tools_by_name.get(normalized_name)
        if existing is None:
            self._tools_by_name[normalized_name] = normalized_tool
            self._tool_observations.setdefault(normalized_name, (0, 0))
            return normalized_tool

        merged_capabilities = sorted(set(existing.capabilities).union(normalized_tool.capabilities))
        merged_tool = ToolCapability(
            tool_name=normalized_name,
            capabilities=merged_capabilities,
            reliability=max(existing.reliability, normalized_tool.reliability),
        )
        self._tools_by_name[normalized_name] = merged_tool
        self._tool_observations.setdefault(normalized_name, (0, 0))
        return merged_tool

    def register_many(self, tools: list[ToolCapability]) -> list[ToolCapability]:
        registered: list[ToolCapability] = []
        for tool in tools:
            registered.append(self.register(tool))
        return registered

    def list_tools(self) -> list[ToolCapability]:
        return sorted(
            (tool.model_copy(deep=True) for tool in self._tools_by_name.values()),
            key=lambda item: item.tool_name.lower(),
        )

    def record_execution(self, *, tool_name: str, success: bool) -> None:
        normalized_name = _normalize_tool_name(tool_name)
        if normalized_name not in self._tools_by_name:
            return
        observed_successes, observed_total = self._tool_observations.get(normalized_name, (0, 0))
        next_successes = observed_successes + (1 if success else 0)
        next_total = observed_total + 1
        self._tool_observations[normalized_name] = (next_successes, next_total)

    def get_observation_counts(self, tool_name: str) -> tuple[int, int]:
        normalized_name = _normalize_tool_name(tool_name)
        return self._tool_observations.get(normalized_name, (0, 0))

    def select_for_step(self, step: ExecutionStep, min_reliability: float) -> ToolCapability | None:
        return select_mcp_tool(step=step, tools=self._list_tools_for_selection(), min_reliability=min_reliability)

    def _list_tools_for_selection(self) -> list[ToolCapability]:
        selection_tools: list[ToolCapability] = []
        for tool in self.list_tools():
            observed_successes, observed_total = self._tool_observations.get(tool.tool_name, (0, 0))
            if observed_total <= 0:
                adjusted_reliability = tool.reliability
            else:
                observed_success_rate = observed_successes / observed_total
                adjusted_reliability = (0.7 * tool.reliability) + (0.3 * observed_success_rate)
            selection_tools.append(
                ToolCapability(
                    tool_name=tool.tool_name,
                    capabilities=list(tool.capabilities),
                    reliability=min(max(adjusted_reliability, 0.0), 1.0),
                )
            )
        return selection_tools


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_capability: str = Field(min_length=1)


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    track: AcquisitionTrack
    executor: str = Field(min_length=1)
    success: bool
    output: str = Field(default="")


class ModuleMainResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1)
    steps: list[ExecutionStep]
    step_results: list[StepResult]
    memory_updates: list[str] = Field(default_factory=list)
    reflection: str = Field(min_length=1)
    next_investment_area: str = Field(min_length=1)


ToolExecutor = Callable[[ExecutionStep, ToolCapability], Awaitable[StepResult]]
SelfProgrammingExecutor = Callable[[ExecutionStep], Awaitable[StepResult]]


class ModuleMainOrchestrator:
    def __init__(
        self,
        *,
        tool_executor: ToolExecutor,
        self_programming_executor: SelfProgrammingExecutor,
        min_tool_reliability: float = 0.6,
    ) -> None:
        if isinstance(min_tool_reliability, bool) or not isinstance(min_tool_reliability, (int, float)):
            raise ValueError("min_tool_reliability must be a float between 0.0 and 1.0")
        if not 0.0 <= min_tool_reliability <= 1.0:
            raise ValueError("min_tool_reliability must be between 0.0 and 1.0")
        self.tool_executor = tool_executor
        self.self_programming_executor = self_programming_executor
        self.min_tool_reliability = float(min_tool_reliability)

    async def run(self, task: str, tools: list[ToolCapability] | None = None) -> ModuleMainResult:
        normalized_task = _normalize_task_text(task)

        steps = decompose_task(normalized_task)
        available_tools = tools or []
        results: list[StepResult] = []

        for step in steps:
            selected_tool = select_mcp_tool(step=step, tools=available_tools, min_reliability=self.min_tool_reliability)
            if selected_tool is not None:
                try:
                    tool_result = await self.tool_executor(step, selected_tool)
                    normalized_tool_result = self._normalize_step_result(
                        step=step,
                        result=self._coerce_step_result(tool_result),
                        default_track=AcquisitionTrack.MCP_TOOL,
                        default_executor=selected_tool.tool_name,
                    )
                except Exception:
                    result = await self._safe_self_programming_result(step)
                else:
                    if normalized_tool_result.success:
                        result = normalized_tool_result
                    else:
                        result = await self._safe_self_programming_result(step)
            else:
                result = await self._safe_self_programming_result(step)
            results.append(result)

        memory_updates = [
            f"{result.step_id}:{result.track.value}:{'ok' if result.success else 'fail'}"
            for result in results
        ]
        reflection = summarize_reflection(results)
        next_investment_area = recommend_next_investment(results)

        return ModuleMainResult(
            task=normalized_task,
            steps=steps,
            step_results=results,
            memory_updates=memory_updates,
            reflection=reflection,
            next_investment_area=next_investment_area,
        )

    async def run_with_registry(self, task: str, registry: ToolLearningRegistry) -> ModuleMainResult:
        if not isinstance(registry, ToolLearningRegistry):
            raise TypeError("registry must be a ToolLearningRegistry instance")
        normalized_task = _normalize_task_text(task)

        steps = decompose_task(normalized_task)
        results: list[StepResult] = []

        for step in steps:
            selected_tool = registry.select_for_step(step=step, min_reliability=self.min_tool_reliability)
            if selected_tool is not None:
                try:
                    tool_result = await self.tool_executor(step, selected_tool)
                    normalized_tool_result = self._normalize_step_result(
                        step=step,
                        result=self._coerce_step_result(tool_result),
                        default_track=AcquisitionTrack.MCP_TOOL,
                        default_executor=selected_tool.tool_name,
                    )
                except Exception:
                    registry.record_execution(tool_name=selected_tool.tool_name, success=False)
                    result = await self._safe_self_programming_result(step)
                else:
                    registry.record_execution(
                        tool_name=selected_tool.tool_name,
                        success=normalized_tool_result.success,
                    )
                    if normalized_tool_result.success:
                        result = normalized_tool_result
                    else:
                        result = await self._safe_self_programming_result(step)
            else:
                result = await self._safe_self_programming_result(step)
            results.append(result)

        memory_updates = [
            f"{result.step_id}:{result.track.value}:{'ok' if result.success else 'fail'}"
            for result in results
        ]
        reflection = summarize_reflection(results)
        next_investment_area = recommend_next_investment(results)

        return ModuleMainResult(
            task=normalized_task,
            steps=steps,
            step_results=results,
            memory_updates=memory_updates,
            reflection=reflection,
            next_investment_area=next_investment_area,
        )

    async def _safe_self_programming_result(self, step: ExecutionStep) -> StepResult:
        try:
            result = await self.self_programming_executor(step)
            normalized_result = self._normalize_step_result(
                step=step,
                result=self._coerce_step_result(result),
                default_track=AcquisitionTrack.SELF_PROGRAMMING,
                default_executor="self_programming_engine",
            )
        except Exception as error:
            return StepResult(
                step_id=step.step_id,
                track=AcquisitionTrack.SELF_PROGRAMMING,
                executor="self_programming_engine",
                success=False,
                output=f"self_programming_exception:{error.__class__.__name__}",
            )
        return normalized_result

    def _normalize_step_result(
        self,
        *,
        step: ExecutionStep,
        result: StepResult,
        default_track: AcquisitionTrack,
        default_executor: str,
    ) -> StepResult:
        step_id = result.step_id if result.step_id == step.step_id else step.step_id
        track = result.track if result.track == default_track else default_track
        executor = result.executor.strip() if result.executor.strip() else default_executor
        return StepResult(
            step_id=step_id,
            track=track,
            executor=executor,
            success=result.success,
            output=result.output,
        )

    def _coerce_step_result(self, result: Any) -> StepResult:
        if isinstance(result, StepResult):
            return result
        return StepResult.model_validate(result)


def decompose_task(task: str) -> list[ExecutionStep]:
    stripped_task = _normalize_task_text(task)

    normalized = re.sub(r"(?:^|\n)\s*[-*•]\s+", ".", stripped_task)
    normalized = re.sub(r"(?:^|\n)\s*\d+\s*[\)\.、）]\s+", ".", normalized)
    normalized = (
        normalized.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", ".")
        .replace(",", ".")
        .replace("，", ".")
        .replace(";", ".")
        .replace("；", ".")
        .replace(":", ".")
        .replace("：", ".")
        .replace("?", ".")
        .replace("？", ".")
        .replace("!", ".")
        .replace("！", ".")
        .replace("。", ".")
        .replace("、", ".")
        .replace("|", ".")
    )
    parts = [part.strip(" .") for part in normalized.split(".") if part.strip(" .")]
    if not parts:
        parts = [stripped_task]
    parts = _split_by_connectors(parts)

    steps: list[ExecutionStep] = []
    for index, part in enumerate(parts, start=1):
        capability = _infer_required_capability(part)
        steps.append(
            ExecutionStep(
                step_id=f"step_{index:02d}",
                description=part,
                required_capability=capability,
            )
        )
    return steps


def _split_by_connectors(parts: list[str]) -> list[str]:
    split_parts: list[str] = []
    connector_pattern = re.compile(
        r"\b(?:and|then)\b|\s+&\s+|\s+/\s+|->|以及|并且|然后|与",
        flags=re.IGNORECASE,
    )
    ambiguous_connector_pattern = re.compile(r"[并及再]")
    for part in parts:
        normalized_part = part.strip()
        if not normalized_part:
            continue
        candidates = [
            item.strip(" .")
            for item in connector_pattern.split(normalized_part)
            if item.strip(" .")
        ]
        if len(candidates) >= 2:
            split_parts.extend(candidates)
            continue
        ambiguous_candidates = [
            item.strip(" .")
            for item in ambiguous_connector_pattern.split(normalized_part)
            if item.strip(" .")
        ]
        if len(ambiguous_candidates) >= 2 and _is_valid_ambiguous_split(ambiguous_candidates):
            split_parts.extend(ambiguous_candidates)
        else:
            split_parts.append(normalized_part)
    return split_parts


def _is_valid_ambiguous_split(parts: list[str]) -> bool:
    return all(_infer_required_capability(part) != "general" for part in parts)


def select_mcp_tool(
    *,
    step: ExecutionStep,
    tools: list[ToolCapability],
    min_reliability: float,
) -> ToolCapability | None:
    if isinstance(min_reliability, bool) or not isinstance(min_reliability, (int, float)):
        raise ValueError("min_reliability must be a float between 0.0 and 1.0")
    if not 0.0 <= min_reliability <= 1.0:
        raise ValueError("min_reliability must be between 0.0 and 1.0")
    normalized_min_reliability = float(min_reliability)

    capability = _normalize_capability(step.required_capability)
    if not capability:
        return None
    if capability == AcquisitionTrack.SELF_PROGRAMMING.value:
        return None

    exact_candidates = []
    general_candidates = []
    for tool in tools:
        if tool.reliability < normalized_min_reliability:
            continue
        capabilities = {
            normalized_capability
            for item in tool.capabilities
            if item.strip()
            for normalized_capability in [_normalize_capability(item)]
            if normalized_capability
        }
        if not capabilities:
            capabilities = {"general"}
        if capability in capabilities:
            exact_candidates.append(tool)
        elif "general" in capabilities:
            general_candidates.append(tool)

    candidates = exact_candidates or general_candidates
    if not candidates:
        return None

    return sorted(candidates, key=lambda item: (-item.reliability, item.tool_name.lower(), item.tool_name))[0]


def summarize_reflection(results: list[StepResult]) -> str:
    if not results:
        return "No execution steps were produced."
    success_count = sum(1 for item in results if item.success)
    total = len(results)
    mcp_count = sum(1 for item in results if item.track == AcquisitionTrack.MCP_TOOL)
    sp_count = total - mcp_count
    return (
        f"Executed {total} steps with {success_count} successes; "
        f"MCP steps={mcp_count}, self_programming steps={sp_count}."
    )


def recommend_next_investment(results: list[StepResult]) -> str:
    if not results:
        return "task_decomposition"

    failed_self_programming = any(
        item.track == AcquisitionTrack.SELF_PROGRAMMING and not item.success
        for item in results
    )
    failed_mcp = any(item.track == AcquisitionTrack.MCP_TOOL and not item.success for item in results)

    if failed_self_programming:
        return "self_programming_engine"
    if failed_mcp:
        return "tool_learning"

    used_self_programming = any(item.track == AcquisitionTrack.SELF_PROGRAMMING for item in results)
    if used_self_programming:
        return "mcp_coverage_expansion"
    return "execution_efficiency"


def _infer_required_capability(text: str) -> str:
    lowered_text = text.lower()
    if any(keyword in lowered_text for keyword in ("生成", "开发", "构建", "实现", "编写代码", "代码")):
        return "self_programming"
    if any(keyword in lowered_text for keyword in ("桌面", "浏览器", "自动化", "界面")):
        return "desktop_automation"
    if any(keyword in lowered_text for keyword in ("法律", "合同", "合规")):
        return "legal_reasoning"
    if any(keyword in lowered_text for keyword in ("交易", "市场", "投资组合")):
        return "trading_ops"
    if any(keyword in lowered_text for keyword in ("搜索", "研究", "检索")):
        return "research"

    tokens = re.findall(r"[a-z0-9_]+", text.lower().replace("-", " "))
    if not tokens:
        return "general"
    if any(
        token
        in {
            "generate",
            "build",
            "implement",
            "implementation",
            "develop",
            "code",
            "coding",
            "program",
            "programming",
            "algorithm",
            "script",
        }
        for token in tokens
    ):
        return "self_programming"
    for token in tokens:
        if token in {"desktop", "browser", "ui", "automation"}:
            return "desktop_automation"
        if token in {"legal", "contract", "compliance"}:
            return "legal_reasoning"
        if token in {"trade", "trading", "market", "portfolio"}:
            return "trading_ops"
        if token in {"search", "research", "retrieve"}:
            return "research"
    return "general"


def _normalize_capability(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def _normalize_tool_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip("_")
    if not normalized:
        raise ValueError("tool_name must include at least one alphanumeric character")
    return normalized


def _normalize_task_text(task: str) -> str:
    if isinstance(task, bool) or not isinstance(task, str):
        raise TypeError("task must be a string")
    normalized = task.strip()
    if not normalized:
        raise ValueError("task must not be empty")
    return normalized
