from __future__ import annotations

from types import SimpleNamespace

from quentin.council.manager import _resolve_council_timeout_for_route


def test_local_council_timeout_respects_explicit_local_override(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", "90")
    monkeypatch.setenv("QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S", "45")

    route = SimpleNamespace(provider="ollama", base_url="http://localhost:11434")

    assert _resolve_council_timeout_for_route(route=route, is_arbiter=False) == 45.0


def test_local_council_timeout_falls_back_to_base_without_forced_floor(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", "90")
    monkeypatch.delenv("QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S", raising=False)
    monkeypatch.delenv("QUENTIN_COUNCIL_MEMBER_TIMEOUT_S", raising=False)

    route = SimpleNamespace(provider="ollama", base_url="http://localhost:11434")

    assert _resolve_council_timeout_for_route(route=route, is_arbiter=False) == 90.0
