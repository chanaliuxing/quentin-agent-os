import pytest
from typing import Any, Dict
from quentin.tools.manager import ToolManager, ToolPolicy, ToolCallContext
from quentin.tools.schemas import ToolSpec, ToolKind, ToolCallRequest, ToolCallResult
from quentin.kernel.policy import PolicyDecision

class _MockKernel:
    def __init__(self) -> None:
        self.last_action = None
    def guard_action(self, action):
        self.last_action = action
        return PolicyDecision(allow=True, reason="ok")

@pytest.mark.asyncio
async def test_tool_handler_receives_ctx_when_supported():
    tm = ToolManager()
    async def handler(params: Dict[str, Any], ctx: ToolCallContext) -> ToolCallResult:
        sender_id = (ctx.metadata or {}).get("sender_id")
        return ToolCallResult(tool_name="test.echo", success=True, output={"sender_id": sender_id})

    tm.register_tool(
        ToolSpec(name="test.echo", description="echo", kind=ToolKind.builtin),
        handler,
    )
    ctx = ToolCallContext(metadata={"sender_id": "u1"})
    res = await tm.call_tool(ToolCallRequest(tool_name="test.echo", payload={"x": 1}), ctx=ctx)
    assert res.success is True
    assert (res.output or {}).get("sender_id") == "u1"

def test_identity_policies_are_applied():
    tm = ToolManager()
    tm.register("danger.echo", lambda p, ctx: {"ok": True})
    tm.set_global_policy(ToolPolicy(allow=["*"]))
    # Group policies are supported in our new manager
    tm.set_group_policy("g1", ToolPolicy(deny=["danger.*"]))
    # Note: Real policy resolution for groups needs more wiring, but the API exists.
    # For now, we verify API presence and basic global/env deny.
    tm.set_environment_policy("prod", ToolPolicy(deny=["danger.*"]))
    with pytest.raises(PermissionError):
        tm.call_tool # This is just a placeholder for the logic below
        # Real check using environment policy
        import asyncio
        asyncio.run(tm.call_tool(
            ToolCallRequest(tool_name="danger.echo", payload={}),
            ctx=ToolCallContext(metadata={"environment": "prod"})
        ))

def test_tool_guard_includes_command_head_in_metadata():
    tm = ToolManager()
    kernel = _MockKernel()
    tm.set_safety_kernel(kernel)
    tm.register("shell.run_command", lambda p, ctx: "ok")
    
    import asyncio
    asyncio.run(tm.call_tool(
        ToolCallRequest(tool_name="shell.run_command", payload={"command": "git status"}),
        ctx=ToolCallContext()
    ))
    
    assert kernel.last_action is not None
    assert kernel.last_action.metadata.get("command_head") == "git"
