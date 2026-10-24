from __future__ import annotations

from types import SimpleNamespace

from quentin.llm import client as llm_client


def test_call_llm_applies_prompt_dialect_before_remote_payload(monkeypatch) -> None:
    captured = {}

    def _fake_apply_prompt_dialect(*, provider, model_name, system_prompt, user_prompt, action_metadata):
        _ = (provider, model_name, action_metadata)
        return f"[sp]{system_prompt}", f"[up]{user_prompt}"

    def _fake_post_with_retry(*, url, payload, headers, timeout_s):
        _ = (url, headers, timeout_s)
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_client, "_apply_prompt_dialect", _fake_apply_prompt_dialect)
    monkeypatch.setattr(llm_client, "_post_with_retry", _fake_post_with_retry)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    out = llm_client.call_llm(
        SimpleNamespace(provider="openai", name="gpt-x"),
        user_prompt="user text",
        system_prompt="system text",
        provider="openai",
        model_name="gpt-x",
    )
    assert out == "ok"
    messages = captured["payload"]["messages"]
    assert messages[0]["content"] == "[sp]system text"
    assert messages[1]["content"] == "[up]user text"

