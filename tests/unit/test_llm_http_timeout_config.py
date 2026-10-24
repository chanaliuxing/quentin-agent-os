from __future__ import annotations

import httpx

from quentin.llm.client import _build_http_timeout


def test_build_http_timeout_uses_local_read_budget(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_OLLAMA_READ_TIMEOUT_S", "7")

    timeout = _build_http_timeout(timeout_s=90, base_url="http://localhost:11434", stream=True)

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 7.0
    assert timeout.connect == 10.0


def test_build_http_timeout_caps_read_by_total(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_OLLAMA_READ_TIMEOUT_S", "20")

    timeout = _build_http_timeout(timeout_s=5, base_url="http://localhost:11434", stream=True)

    assert timeout.read == 5.0
    assert timeout.write == 5.0


def test_build_http_timeout_allows_disabling_local_read_timeout(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_OLLAMA_READ_TIMEOUT_S", "0")

    timeout = _build_http_timeout(timeout_s=90, base_url="http://localhost:11434", stream=True)

    assert timeout.read is None
    assert timeout.connect == 10.0
