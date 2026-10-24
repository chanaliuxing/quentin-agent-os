from __future__ import annotations

from scripts import run_canary_brain_once as canary


def test_apply_offline_smoke_env_sets_expected_flags(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_LLM_FORCE_STUB", raising=False)
    monkeypatch.delenv("LLM_STUB", raising=False)
    monkeypatch.delenv("QUENTIN_BRAIN_RUN_SLEEP", raising=False)
    monkeypatch.delenv("QUENTIN_BRAIN_RUN_IMMUNE", raising=False)

    canary._apply_offline_smoke_env()

    assert canary.os.environ.get("QUENTIN_LLM_FORCE_STUB") == "1"
    assert canary.os.environ.get("LLM_STUB") == "1"
    assert canary.os.environ.get("QUENTIN_BRAIN_RUN_SLEEP") == "1"
    assert canary.os.environ.get("QUENTIN_BRAIN_RUN_IMMUNE") == "1"
