from __future__ import annotations

import pytest

from quentin.tools.manager import ToolCallContext, ToolManager
from quentin.tools.schemas import ToolCallRequest, ToolCallResult, ToolKind, ToolSpec


@pytest.mark.asyncio
async def test_tool_manager_supports_request_style_handler() -> None:
    tm = ToolManager()

    async def _handler(req: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(
            tool_name=req.tool_name,
            success=True,
            output={"echo": req.payload.get("x")},
        )

    tm.register_tool(
        ToolSpec(name="test.request_style", description="request style", kind=ToolKind.builtin),
        _handler,
    )

    res = await tm.call_tool(
        ToolCallRequest(tool_name="test.request_style", payload={"x": 7}),
        ctx=ToolCallContext(metadata={"session_id": "t1"}),
    )
    assert res.success is True
    assert (res.output or {}).get("echo") == 7

