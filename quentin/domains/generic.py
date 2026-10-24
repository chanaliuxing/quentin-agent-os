from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.tools.manager import ToolManager
from quentin.tools.schemas import (
    ToolSpec,
    ToolKind,
    ToolCallRequest,
    ToolCallResult,
)
from quentin.tools.manager import ToolCallContext
from quentin.domains.base import DomainAdapter, DomainTask


SCRATCHPAD_KEY = "generic:scratchpad:entries"


@dataclass
class GenericDomainAdapter(DomainAdapter):
    """
    内置的 “通用领域”：
    - 不依赖任何外部系统
    - 提供少量示例工具，方便测试 / Demo / Prompt 调用
    """
    tracer: Tracer
    kv: KVStore

    name: str = "generic"
    description: str = "Built-in generic domain with basic echo & scratchpad tools."

    async def register_tools(self, tool_manager: ToolManager) -> None:
        # 1) echo 工具
        echo_spec = ToolSpec(
            name="generic.echo",
            description="Echo back the input text. Useful for testing tool-calls.",
            kind=ToolKind.builtin,
            domain=self.name,
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            output_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        )

        async def echo_handler(req: ToolCallRequest) -> ToolCallResult:
            txt = str(req.payload.get("text", ""))
            return ToolCallResult(
                tool_name=req.tool_name,
                success=True,
                output={"text": txt},
            )

        tool_manager.register_tool(echo_spec, echo_handler)

        # 2) scratchpad.append
        append_spec = ToolSpec(
            name="generic.scratchpad.append",
            description="Append a line of text into a persistent scratchpad.",
            kind=ToolKind.builtin,
            domain=self.name,
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

        async def append_handler(req: ToolCallRequest) -> ToolCallResult:
            text = str(req.payload.get("text", ""))
            entries: List[str] = await self.kv.get(SCRATCHPAD_KEY) or []
            entries.append(text)
            await self.kv.save(SCRATCHPAD_KEY, entries)
            return ToolCallResult(
                tool_name=req.tool_name,
                success=True,
                output={"count": len(entries)},
            )

        tool_manager.register_tool(append_spec, append_handler)

        # 3) scratchpad.list
        list_spec = ToolSpec(
            name="generic.scratchpad.list",
            description="List recent lines from the scratchpad.",
            kind=ToolKind.builtin,
            domain=self.name,
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        )

        async def list_handler(req: ToolCallRequest) -> ToolCallResult:
            limit = int(req.payload.get("limit", 20))
            entries: List[str] = await self.kv.get(SCRATCHPAD_KEY) or []
            entries = entries[-limit:]
            return ToolCallResult(
                tool_name=req.tool_name,
                success=True,
                output={"entries": entries},
            )

        tool_manager.register_tool(list_spec, list_handler)

    async def handle_task(
        self,
        task: DomainTask,
        tool_manager: ToolManager,
    ) -> Dict[str, Any]:
        """
        MVP：直接调用 generic.scratchpad.append 记录一行，然后用 echo 返回。
        将来 Planner 可以把 DomainTask 进一步拆成 Tool 调用序列。
        """
        # 简单 demo：把 goal + input 写入 scratchpad
        payload = {"text": f"{task.goal} | input={task.input}"}
        await tool_manager.call_tool(
            ToolCallRequest(tool_name="generic.scratchpad.append", payload=payload),
            ctx=ToolCallContext(
                metadata={
                    "domain": task.domain,
                    "environment": task.meta.get("environment", "sandbox"),
                    "risk_level": task.meta.get("risk_level", "low"),
                }
            ),
        )

        # 再 echo 一下 goal，当作返回结果
        result = await tool_manager.call_tool(
            ToolCallRequest(tool_name="generic.echo", payload={"text": task.goal}),
            ctx=ToolCallContext(
                metadata={
                    "domain": task.domain,
                    "environment": task.meta.get("environment", "sandbox"),
                    "risk_level": task.meta.get("risk_level", "low"),
                }
            ),
        )
        return {
            "domain": self.name,
            "goal": task.goal,
            "input": task.input,
            "tool_result": result.model_dump(),
        }
