from __future__ import annotations

import asyncio

from quentin.tools.manager import ToolManager
from quentin.tools.schemas import ToolCallRequest, ToolKind, ToolSpec


def test_tool_manager_wraps_untrusted_output() -> None:
    tm = ToolManager()

    def handler(payload, ctx=None):  # noqa: ARG001
        return {"status": "ok", "echo": payload.get("x", 0)}

    spec = ToolSpec(
        name="demo.untrusted",
        description="demo",
        kind=ToolKind.builtin,
        meta={"output_trust": "untrusted"},
    )
    tm.register_tool(spec, lambda req, ctx=None: handler(req.payload, ctx))

    res = asyncio.run(tm.call_tool(ToolCallRequest(tool_name="demo.untrusted", payload={"x": 3})))
    assert res.success is True
    assert isinstance(res.output, dict)
    assert "_untrusted_wrapped_text" in (res.output or {})
