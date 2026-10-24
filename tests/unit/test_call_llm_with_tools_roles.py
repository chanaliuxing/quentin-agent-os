from types import SimpleNamespace


def test_call_llm_with_tools_preserves_system_role(monkeypatch):
    from quentin.llm import client as llm_client

    captured = {}

    class FakeOllamaClient:
        def __init__(self, cfg):  # noqa: ANN001
            self.cfg = cfg

        def chat_with_tools(self, **kwargs):  # noqa: ANN001
            captured["messages"] = kwargs.get("messages")
            captured["tools"] = kwargs.get("tools")
            return {"content": "", "tool_calls": [], "raw": {}}

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(llm_client, "OllamaClient", FakeOllamaClient)
    monkeypatch.setattr(llm_client, "_log_llm_raw_event", lambda **_: None)

    cfg = SimpleNamespace(name="qwen3-vl:latest", provider="ollama", base_url="http://localhost:11434")
    llm_client.call_llm_with_tools(
        cfg,
        system_prompt="SYSTEM RULES",
        user_prompt="USER TASK",
        tools=[{"type": "function", "function": {"name": "ls", "parameters": {"type": "object"}}}],
        provider="ollama",
        model_name="qwen3-vl:latest",
        actor="test",
    )

    msgs = captured["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "SYSTEM RULES"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "USER TASK"

