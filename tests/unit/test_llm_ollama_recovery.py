from __future__ import annotations

import json
import time

import pytest

from quentin.llm import client as mod


def test_call_llm_retries_blank_ollama_response(monkeypatch) -> None:
    attempts = {"count": 0}

    class _FakeClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self._last_raw_response = {"response": "", "done": True}

        def complete(self, prompt: str, timeout: float | None = None, history=None) -> str:  # type: ignore[no-untyped-def]
            _ = prompt
            _ = timeout
            _ = history
            attempts["count"] += 1
            if attempts["count"] == 1:
                self._last_raw_response = {"response": "", "done": True}
                return ""
            self._last_raw_response = {"response": "OK", "done": True}
            return "OK"

    monkeypatch.setattr(mod, "OllamaClient", _FakeClient)
    monkeypatch.setattr(mod, "_guard_and_audit_start", lambda **kwargs: (None, "action"))
    monkeypatch.setattr(mod, "_audit_finish", lambda **kwargs: None)
    monkeypatch.setattr(mod, "_sleep_brief_backoff", lambda attempt: None)
    monkeypatch.setenv("QUENTIN_OLLAMA_RECOVERY_ATTEMPTS", "2")

    out = mod.call_llm(
        config="qwen3.5:9b",
        user_prompt="hello",
        system_prompt="system",
        provider="ollama",
    )

    assert out == "OK"
    assert attempts["count"] == 2


def test_call_llm_raises_after_exhausting_blank_ollama_response(monkeypatch) -> None:
    attempts = {"count": 0}

    class _FakeClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self._last_raw_response = {"response": "", "done": True}

        def complete(self, prompt: str, timeout: float | None = None, history=None) -> str:  # type: ignore[no-untyped-def]
            _ = prompt
            _ = timeout
            _ = history
            attempts["count"] += 1
            self._last_raw_response = {"response": "", "done": True}
            return ""

    monkeypatch.setattr(mod, "OllamaClient", _FakeClient)
    monkeypatch.setattr(mod, "_guard_and_audit_start", lambda **kwargs: (None, "action"))
    monkeypatch.setattr(mod, "_audit_finish", lambda **kwargs: None)
    monkeypatch.setattr(mod, "_sleep_brief_backoff", lambda attempt: None)
    monkeypatch.setenv("QUENTIN_OLLAMA_RECOVERY_ATTEMPTS", "2")
    monkeypatch.delenv("LLM_MODEL_CRITIC", raising=False)

    with pytest.raises(RuntimeError, match="empty_response"):
        mod.call_llm(
            config="qwen3.5:9b",
            user_prompt="hello",
            system_prompt="system",
            provider="ollama",
        )

    assert attempts["count"] == 2


def test_call_llm_switches_to_critic_model_after_recoverable_failures(monkeypatch) -> None:
    attempts: list[str] = []

    class _FakeClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self.name = str(getattr(cfg, "name", ""))
            self._last_raw_response = {"response": "", "done": True}

        def complete(self, prompt: str, timeout: float | None = None, history=None) -> str:  # type: ignore[no-untyped-def]
            _ = prompt
            _ = timeout
            _ = history
            attempts.append(self.name)
            if self.name == "qwen3.5:9b":
                self._last_raw_response = {"response": "", "done": True}
                return ""
            self._last_raw_response = {"response": "OK_CRITIC", "done": True}
            return "OK_CRITIC"

    monkeypatch.setattr(mod, "OllamaClient", _FakeClient)
    monkeypatch.setattr(mod, "_guard_and_audit_start", lambda **kwargs: (None, "action"))
    monkeypatch.setattr(mod, "_audit_finish", lambda **kwargs: None)
    monkeypatch.setattr(mod, "_sleep_brief_backoff", lambda attempt: None)
    monkeypatch.setenv("QUENTIN_OLLAMA_RECOVERY_ATTEMPTS", "1")
    monkeypatch.setenv("LLM_MODEL_CRITIC", "qwen3.5:35b-a3b")

    out = mod.call_llm(
        config="qwen3.5:9b",
        user_prompt="hello",
        system_prompt="system",
        provider="ollama",
    )

    assert out == "OK_CRITIC"
    assert attempts == ["qwen3.5:9b", "qwen3.5:35b-a3b"]


def test_ollama_complete_raises_on_blank_visible_stream(monkeypatch) -> None:
    class _FakeResponse:
        status_code = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def iter_lines(self):  # type: ignore[no-untyped-def]
            yield json.dumps({"response": "", "done": False})
            yield json.dumps({"response": "", "done": True})

        def read(self) -> bytes:
            return b""

    class _FakeHttpClient:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def stream(self, method: str, url: str, json=None):  # type: ignore[no-untyped-def]
            _ = method
            _ = url
            _ = json
            return _FakeResponse()

    monkeypatch.setattr(mod.httpx, "Client", _FakeHttpClient)

    client = mod.OllamaClient(type("Cfg", (), {"name": "qwen3.5:9b", "base_url": "http://localhost:11434"})())

    with pytest.raises(RuntimeError, match="empty_response"):
        client.complete("hello", timeout=30)


def test_ollama_complete_raises_on_first_token_timeout(monkeypatch) -> None:
    class _FakeResponse:
        status_code = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def iter_lines(self):  # type: ignore[no-untyped-def]
            time.sleep(2.0)
            if False:
                yield ""

        def read(self) -> bytes:
            return b""

    class _FakeHttpClient:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def stream(self, method: str, url: str, json=None):  # type: ignore[no-untyped-def]
            _ = method
            _ = url
            _ = json
            return _FakeResponse()

    monkeypatch.setattr(mod.httpx, "Client", _FakeHttpClient)
    monkeypatch.setenv("QUENTIN_OLLAMA_FIRST_TOKEN_TIMEOUT_S", "0.1")

    client = mod.OllamaClient(type("Cfg", (), {"name": "qwen3.5:9b", "base_url": "http://localhost:11434"})())

    with pytest.raises(RuntimeError, match="first_token_timeout"):
        client.complete("hello", timeout=30)


def test_call_llm_retries_first_token_timeout(monkeypatch) -> None:
    attempts = {"count": 0}

    class _FakeClient:
        def __init__(self, cfg):  # type: ignore[no-untyped-def]
            self._last_raw_response = None

        def complete(self, prompt: str, timeout: float | None = None, history=None) -> str:  # type: ignore[no-untyped-def]
            _ = prompt
            _ = timeout
            _ = history
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("first_token_timeout: no stream chunk received within 45s")
            self._last_raw_response = {"response": "OK", "done": True}
            return "OK"

    monkeypatch.setattr(mod, "OllamaClient", _FakeClient)
    monkeypatch.setattr(mod, "_guard_and_audit_start", lambda **kwargs: (None, "action"))
    monkeypatch.setattr(mod, "_audit_finish", lambda **kwargs: None)
    monkeypatch.setattr(mod, "_sleep_brief_backoff", lambda attempt: None)
    monkeypatch.setenv("QUENTIN_OLLAMA_RECOVERY_ATTEMPTS", "2")

    out = mod.call_llm(
        config="qwen3.5:9b",
        user_prompt="hello",
        system_prompt="system",
        provider="ollama",
    )

    assert out == "OK"
    assert attempts["count"] == 2
