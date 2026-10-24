from __future__ import annotations

from quentin.infra.llm.parameter_scaler import ParameterScaler


def test_parameter_scaler_applies_failure_boost() -> None:
    out = ParameterScaler.scale(base_params={"temperature": 0.0, "top_p": 0.9}, failure_count=2, last_error="")
    assert float(out.get("temperature") or 0.0) >= 0.2


def test_parameter_scaler_token_hedge_reduces_entropy(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PARAM_SCALER_TOKEN_HEDGE_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PARAM_SCALER_HIGH_WATERMARK", "0.75")
    out = ParameterScaler.scale(
        base_params={"temperature": 0.7, "top_p": 0.95},
        failure_count=0,
        token_usage=110000,
        context_window=128000,
    )
    assert float(out.get("temperature") or 0.0) < 0.7
    assert float(out.get("top_p") or 1.0) <= 0.8


def test_parameter_scaler_applies_model_profile_cap(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PARAM_SCALER_PROFILE_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PARAM_SCALER_TEMP_MAX_QWEN", "0.6")
    out = ParameterScaler.scale(
        base_params={"temperature": 0.9, "top_p": 0.95},
        failure_count=0,
        model_name="qwen3",
    )
    assert float(out.get("temperature") or 0.0) <= 0.6


def test_parameter_scaler_failure_history_downshift(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PARAM_SCALER_FAILURE_DOWNSHIFT_THRESHOLD", "3")
    out = ParameterScaler.scale(
        base_params={"temperature": 0.8, "top_p": 0.95},
        failure_count=3,
        last_error="timeout waiting backend",
    )
    assert float(out.get("temperature") or 0.0) < 0.8
    assert float(out.get("top_p") or 1.0) <= 0.82
