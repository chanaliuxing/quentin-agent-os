from __future__ import annotations

from quentin.llm.client import OllamaClient


def test_ollama_stream_billing_bypass_localhost_default(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_BILLING_BYPASS", raising=False)
    monkeypatch.delenv("QUENTIN_BILLING_ENFORCE_LOCAL_OLLAMA", raising=False)
    assert OllamaClient._stream_billing_bypass_enabled("http://localhost:11434") is True
    assert OllamaClient._stream_billing_bypass_enabled("http://127.0.0.1:11434") is True


def test_ollama_stream_billing_can_enforce_local(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_BILLING_BYPASS", raising=False)
    monkeypatch.setenv("QUENTIN_BILLING_ENFORCE_LOCAL_OLLAMA", "1")
    assert OllamaClient._stream_billing_bypass_enabled("http://localhost:11434") is False


def test_ollama_stream_billing_remote_not_bypassed(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_BILLING_BYPASS", raising=False)
    monkeypatch.delenv("QUENTIN_BILLING_ENFORCE_LOCAL_OLLAMA", raising=False)
    assert OllamaClient._stream_billing_bypass_enabled("https://ollama.remote.internal:11434") is False

