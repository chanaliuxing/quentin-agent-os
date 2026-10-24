from __future__ import annotations

from quentin.tools.manager import ToolManager
from quentin.tools.schemas import ToolKind, ToolSpec, ToolCallRequest, ToolCallResult
from quentin.tools.summary_map import build_tool_summary_map


def test_summary_is_short_and_stable() -> None:
    summary = build_tool_summary_map(
        tool_descriptions={
            "tool.b": "This tool performs a very long and detailed operation across files.",
            "tool.a": "Read small file quickly.",
        },
        max_words=5,
    )
    # stable alphabetical key order and truncation
    keys = list(summary.keys())
    assert keys == ["tool.a", "tool.b"]
    assert summary["tool.a"] == "Read small file quickly."
    assert summary["tool.b"].endswith("...")
    assert len(summary["tool.b"].split()) <= 6  # 5 words + ellipsis token


def test_help_tool_returns_detailed_schema() -> None:
    tm = ToolManager()

    async def _handler(req: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(tool_name=req.tool_name, success=True, output={"ok": True})

    tm.register_tool(
        ToolSpec(
            name="fs.write_file",
            description="Write text to path.",
            kind=ToolKind.builtin,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            output_schema={"type": "object"},
            risk_level="medium",
            lifecycle="active",
        ),
        _handler,
    )

    out = tm.get_tool_schema_help("fs.write_file")
    assert out["status"] == "ok"
    assert out["tool_name"] == "fs.write_file"
    assert "properties" in out["input_schema"]
    assert out["input_schema"]["properties"]["path"]["type"] == "string"
    assert out["risk_level"] == "medium"
    assert out["lifecycle"] == "active"

