from __future__ import annotations

from types import SimpleNamespace

from quentin.llm.client import call_llm_with_tools


def test_call_llm_with_tools_ollama_native(monkeypatch) -> None:
    class _FakeOllamaClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self.cfg = cfg

        def chat_with_tools(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            return {"content": "ok", "tool_calls": [{"function": {"name": "fs.read_file", "arguments": {"path": "a.py"}}}]}

    monkeypatch.setattr("quentin.llm.client.OllamaClient", _FakeOllamaClient)
    cfg = SimpleNamespace(name="qwen3-vl:latest", provider="ollama", base_url="http://localhost:11434")
    out = call_llm_with_tools(
        cfg,
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "fs.read_file"}}],
        provider="ollama",
        model_name="qwen3-vl:latest",
    )
    assert out["content"] == "ok"
    assert isinstance(out.get("tool_calls"), list)


def test_call_llm_with_tools_uses_text_model_for_vl(monkeypatch) -> None:
    captured = {}

    class _FakeOllamaClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            captured["model"] = getattr(cfg, "name", None)

        def chat_with_tools(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            return {"content": "ok", "tool_calls": []}

    monkeypatch.setenv("LLM_TOOL_MODEL", "")  # ensure heuristic path
    monkeypatch.setenv("LLM_TEXT_MODEL", "qwen3-vl:latest")
    monkeypatch.setattr("quentin.llm.client.OllamaClient", _FakeOllamaClient)

    cfg = SimpleNamespace(name="qwen2.5vl:latest", provider="ollama", base_url="http://localhost:11434")
    out = call_llm_with_tools(
        cfg,
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "fs.read_file"}}],
        provider="ollama",
        model_name="qwen2.5vl:latest",
    )
    assert out["content"] == "ok"
    assert captured["model"] == "qwen3-vl:latest"


def test_call_llm_with_tools_retries_when_tools_unsupported(monkeypatch) -> None:
    captured = {"calls": []}

    class _FakeOllamaClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self.model = getattr(cfg, "name", "")

        def chat_with_tools(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            captured["calls"].append(self.model)
            if self.model == "qwen2.5vl:latest":
                raise RuntimeError("Ollama /api/chat error 400: does not support tools")
            return {"content": "ok", "tool_calls": []}

    monkeypatch.setenv("LLM_TOOL_MODEL", "qwen2.5vl:latest")
    monkeypatch.setenv("LLM_TEXT_MODEL", "qwen3-vl:latest")
    monkeypatch.setattr("quentin.llm.client.OllamaClient", _FakeOllamaClient)

    cfg = SimpleNamespace(name="qwen2.5vl:latest", provider="ollama", base_url="http://localhost:11434")
    out = call_llm_with_tools(
        cfg,
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "fs.read_file"}}],
        provider="ollama",
        model_name="qwen2.5vl:latest",
    )
    assert out["content"] == "ok"
    assert captured["calls"] == ["qwen2.5vl:latest", "qwen3-vl:latest"]


def test_call_llm_with_tools_applies_context_budget(monkeypatch) -> None:
    captured = {}

    class _FakeOllamaClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self.cfg = cfg

        def chat_with_tools(self, **kwargs):  # type: ignore[no-untyped-def]
            captured["messages"] = kwargs.get("messages")
            return {"content": "ok", "tool_calls": []}

    def _fake_budget(**kwargs):  # type: ignore[no-untyped-def]
        # Force a change so call_llm_with_tools uses a compacted user message.
        guard = SimpleNamespace(should_block=False, reason=None, total_tokens=1, tokens=8192)
        return "COMPACTED", guard

    monkeypatch.setattr("quentin.llm.client.apply_context_budget", _fake_budget)
    monkeypatch.setattr("quentin.llm.client.OllamaClient", _FakeOllamaClient)

    cfg = SimpleNamespace(name="qwen3-vl:latest", provider="ollama", base_url="http://localhost:11434")
    out = call_llm_with_tools(
        cfg,
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "fs.read_file"}}],
        provider="ollama",
        model_name="qwen3-vl:latest",
    )
    assert out["content"] == "ok"
    assert captured["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "COMPACTED"},
    ]


def test_call_llm_with_tools_fallback_for_non_ollama(monkeypatch) -> None:
    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return '{"status":"ok","result":"fallback_text"}'

    monkeypatch.setattr("quentin.llm.client.call_llm", _fake_call_llm)
    cfg = SimpleNamespace(name="gpt-4o-mini", provider="openai")
    out = call_llm_with_tools(
        cfg,
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "fs.read_file"}}],
        provider="openai",
        model_name="gpt-4o-mini",
    )
    assert out["message"]["content"] == '{"status":"ok","result":"fallback_text"}'
    assert out["tool_calls"] == []
