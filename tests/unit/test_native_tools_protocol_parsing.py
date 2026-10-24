from __future__ import annotations

from quentin.llm.tool_call_protocols.native_tools_protocol import NativeToolsProtocol


def test_native_tools_protocol_normalize_tool_call_parses_noisy_json_args() -> None:
    p = NativeToolsProtocol()
    call = {
        "function": {
            "name": "fs.read_file",
            "arguments": 'noise... {"path":"README.md",} ...tail',
        }
    }
    tc = p._normalize_native_tool_call(call)
    assert isinstance(tc, dict)
    assert tc["tool_name"] == "fs.read_file"
    assert tc["args"]["path"] == "README.md"


def test_native_tools_protocol_normalize_tool_call_handles_invalid_args() -> None:
    p = NativeToolsProtocol()
    call = {"function": {"name": "fs.read_file", "arguments": "not json"}}
    tc = p._normalize_native_tool_call(call)
    assert isinstance(tc, dict)
    assert tc["tool_name"] == "fs.read_file"
    assert tc["args"] == {}
