from __future__ import annotations

import os

import pytest

from quentin.tools.manager import ToolManager, ToolCallContext
from quentin.tools.middleware.error_hints import ErrorHintsMiddleware
from quentin.tools.schemas import ToolSpec, ToolCallRequest


@pytest.mark.asyncio
async def test_error_hints_middleware_normalizes_dict_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TOOL_MIDDLEWARE_PIPELINE", "1")
    tm = ToolManager()
    tm.set_repo_root(str(tmp_path))
    tm.add_middleware(ErrorHintsMiddleware())

    spec = ToolSpec(name="x.dict_error", description="x")

    def _handler(req: ToolCallRequest, ctx: ToolCallContext):
        return {
            "status": "error",
            "error": "Search string not found in foo.py",
            "hint": "read first",
            "next_actions": ["fs.read_file", "use broader token"],
        }

    tm.register_tool(spec, _handler)

    res = await tm.call_tool(ToolCallRequest(tool_name="x.dict_error", payload={}), ToolCallContext(metadata={}))
    assert res.success is False
    assert "Search string not found" in str(res.error or "")
    assert "hint" in res.meta
    assert "next_actions" in res.meta

