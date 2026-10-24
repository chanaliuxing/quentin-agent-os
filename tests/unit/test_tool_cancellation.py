import pytest

from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError
from quentin.tools.manager import ToolManager, ToolCallContext
from quentin.tools.schemas import ToolCallRequest, ToolCallResult, ToolSpec


@pytest.mark.asyncio
async def test_tool_manager_respects_cancel_token() -> None:
    tm = ToolManager()

    async def handler(req: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(tool_name=req.tool_name, success=True, output={"ok": True})

    tm.register_tool(ToolSpec(name="test.ok", description="ok"), handler)

    token = CancellationToken()
    token.cancel("user_cancelled")
    ctx = ToolCallContext(cancel_token=token, metadata={"domain": "core", "environment": "sandbox", "risk_level": "low"})

    with pytest.raises(CancelledError):
        await tm.call_tool(ToolCallRequest(tool_name="test.ok", payload={}), ctx=ctx)

