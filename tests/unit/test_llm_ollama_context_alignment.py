from __future__ import annotations

from dataclasses import dataclass

from quentin.llm import client as llm_client


@dataclass
class _Guard:
    tokens: int = 8192
    total_tokens: int = 100
    reason: str | None = None
    should_block: bool = False


class _DummyOllamaClient:
    def __init__(self, cfg):
        self.config = cfg

    def complete(self, prompt: str, timeout=None):  # noqa: ANN001
        _ = (prompt, timeout)
        return "ok"


def test_call_llm_uses_ollama_num_ctx_for_context_budget(monkeypatch) -> None:
    seen = {}

    def _fake_budget(**kwargs):  # type: ignore[no-untyped-def]
        seen["context_window_tokens"] = kwargs.get("context_window_tokens")
        return kwargs["prompt_text"], _Guard(tokens=kwargs.get("context_window_tokens") or 0)

    monkeypatch.setattr(llm_client, "apply_context_budget", _fake_budget)
    monkeypatch.setattr(llm_client, "OllamaClient", _DummyOllamaClient)
    monkeypatch.setattr(llm_client, "_guard_and_audit_start", lambda **kwargs: (None, "aid"))
    monkeypatch.setattr(llm_client, "_audit_finish", lambda **kwargs: None)

    cfg = type("Cfg", (), {"name": "qwen3-vl:latest", "provider": "ollama", "base_url": "http://localhost:11434"})()
    out = llm_client.call_llm(cfg, user_prompt="hello", system_prompt="system")

    assert out == "ok"
    assert seen["context_window_tokens"] == 8192
