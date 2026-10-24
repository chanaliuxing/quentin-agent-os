from __future__ import annotations

from quentin.llm import client as mod


def test_call_llm_logs_callsite_metadata(monkeypatch) -> None:
    captured = {}

    def _fake_append(entry):  # type: ignore[no-untyped-def]
        captured.update(entry)

    monkeypatch.setattr(mod, "_append_llm_raw_history", _fake_append)

    def _invoke() -> str:
        return mod.call_llm(
            config="stub-model",
            user_prompt="hello",
            system_prompt="world",
            provider="stub",
        )

    _invoke()

    callsite = captured.get("metadata", {}).get("callsite", {})
    assert captured.get("provider") == "stub"
    assert str(callsite.get("function") or "") == "_invoke"
    assert str(callsite.get("file") or "").endswith("test_llm_callsite_trace.py")
    assert int(callsite.get("lineno") or 0) > 0
