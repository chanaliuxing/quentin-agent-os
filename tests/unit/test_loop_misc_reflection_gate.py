from __future__ import annotations

from quentin.cognitive.loop_misc import should_trigger_reflection


def test_should_trigger_reflection_respects_disable_env(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_REFLECTION_ENABLED", "0")
    assert should_trigger_reflection(failure_count=99, metrics={"last_attempt_evaluation": {"severity": "critical"}}) is False


def test_should_trigger_reflection_still_uses_threshold_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_REFLECTION_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_REFLECTION_FAILURE_THRESHOLD", "3")
    assert should_trigger_reflection(failure_count=2, metrics={}) is False
    assert should_trigger_reflection(failure_count=3, metrics={}) is True
