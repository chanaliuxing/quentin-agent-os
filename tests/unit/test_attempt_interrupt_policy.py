from __future__ import annotations

from quentin.cognitive.loop_orchestration import (
    _adaptive_interrupt_cooldown_length,
    _derive_attempt_interrupt_state,
    _interrupt_cooldown_length,
)


def test_interrupt_state_none_when_below_threshold(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_REPEAT_THRESHOLD", "2")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_TOOL_LOOP_THRESHOLD", "3")
    assert _derive_attempt_interrupt_state(repetition_streak=0, tool_loop_streak=1) == "none"


def test_interrupt_state_warn_before_threshold(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_REPEAT_THRESHOLD", "3")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_TOOL_LOOP_THRESHOLD", "4")
    assert _derive_attempt_interrupt_state(repetition_streak=2, tool_loop_streak=0) == "warn"


def test_interrupt_state_interrupt_and_hard_reset(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_REPEAT_THRESHOLD", "2")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_TOOL_LOOP_THRESHOLD", "3")
    assert _derive_attempt_interrupt_state(repetition_streak=2, tool_loop_streak=0) == "interrupt"
    assert _derive_attempt_interrupt_state(repetition_streak=3, tool_loop_streak=0) == "hard_reset"


def test_interrupt_state_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_ENABLED", "0")
    assert _derive_attempt_interrupt_state(repetition_streak=5, tool_loop_streak=5) == "none"


def test_interrupt_cooldown_length(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN", "1")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_HARD_RESET_COOLDOWN", "2")
    assert _interrupt_cooldown_length("interrupt") == 1
    assert _interrupt_cooldown_length("hard_reset") == 2


def test_adaptive_interrupt_cooldown_length(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN", "1")
    monkeypatch.setenv("QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN_MAX", "3")
    out = _adaptive_interrupt_cooldown_length(
        state="interrupt",
        error_subcategory="shell_permission_denied",
        error_origin="environment",
        repetition_streak=2,
        tool_loop_streak=4,
    )
    assert out == 3
