from __future__ import annotations

from quentin.llm.tool_call_protocols import bootstrap_protocols
from quentin.llm.tool_call_protocols.base import ToolCallProtocolRegistry


def test_tool_call_protocol_registry_selects_native_for_ollama(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_EXECUTOR_NATIVE_TOOL_CALLING", "1")
    reg = ToolCallProtocolRegistry()
    bootstrap_protocols(reg)

    p = reg.select(provider="ollama", model_name="qwen2.5:7b", config=object())
    assert p is not None
    assert p.id == "native_tools"


def test_tool_call_protocol_registry_selects_json_fallback_for_non_ollama() -> None:
    reg = ToolCallProtocolRegistry()
    bootstrap_protocols(reg)

    p = reg.select(provider="openai", model_name="gpt-x", config=object())
    assert p is not None
    assert p.id == "json_fallback"

