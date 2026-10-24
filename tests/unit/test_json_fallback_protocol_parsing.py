from __future__ import annotations

import pytest

from quentin.llm.tool_call_protocols.json_fallback_protocol import JsonFallbackProtocol


def test_json_fallback_protocol_robust_parse_handles_markdown_and_trailing_comma() -> None:
    p = JsonFallbackProtocol()
    text = """```json
{"status":"ok","call_tool":{"tool_name":"fs.read_file","args":{"path":"README.md",}},}
```"""
    obj = p._robust_json_parse(text)
    assert isinstance(obj, dict)
    assert obj.get("status") == "ok"


def test_json_fallback_protocol_robust_parse_strips_think_and_final_wrappers() -> None:
    p = JsonFallbackProtocol()
    text = """
<think>long chain of thoughts ...</think>
<final>
{"status":"ok","call_tool":{"tool_name":"fs.read_file","args":{"path":"README.md"}}}
</final>
"""
    obj = p._robust_json_parse(text)
    assert isinstance(obj, dict)
    assert obj.get("status") == "ok"


def test_json_fallback_protocol_normalize_tool_call_parses_string_args() -> None:
    p = JsonFallbackProtocol()
    tc = p._normalize_json_tool_call(
        {"tool_name": "fs.read_file", "args": '{"path":"README.md",}'}
    )
    assert isinstance(tc, dict)
    assert tc["tool_name"] == "fs.read_file"
    assert tc["args"]["path"] == "README.md"


def test_json_fallback_protocol_normalize_tool_call_accepts_name_and_arguments_keys() -> None:
    p = JsonFallbackProtocol()
    tc = p._normalize_json_tool_call(
        {"name": "shell.run_command", "arguments": {"command": "pwd"}}
    )
    assert isinstance(tc, dict)
    assert tc["tool_name"] == "shell.run_command"
    assert tc["args"]["command"] == "pwd"


def test_json_fallback_protocol_normalize_tool_call_synthesizes_top_level_write_args() -> None:
    p = JsonFallbackProtocol()
    tc = p._normalize_json_tool_call(
        {"tool": "fs_write_file", "path": "generated/out.txt", "content": "OK"}
    )
    assert isinstance(tc, dict)
    assert tc["tool_name"] == "fs.write_file"
    assert tc["args"] == {"path": "generated/out.txt", "content": "OK"}


@pytest.mark.asyncio
async def test_json_fallback_protocol_next_action_normalizes_tool_call(monkeypatch) -> None:
    p = JsonFallbackProtocol()

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","call_tool":{"tool_name":"fs.read_file","args":{"path":"README.md"}}}'

    monkeypatch.setattr("quentin.llm.tool_call_protocols.json_fallback_protocol.call_llm", _fake_call_llm)
    decision = await p.next_action(
        system_prompt="s",
        user_prompt="u",
        tools=[],
        config=type("Cfg", (), {"provider": "openai", "name": "gpt"})(),
        context={},
    )
    assert decision.kind == "tool_call"
    assert decision.tool_calls and decision.tool_calls[0]["tool_name"] == "fs.read_file"
