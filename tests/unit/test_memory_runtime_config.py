from __future__ import annotations

from quentin.config.memory_runtime import MemoryRuntimeConfig


def test_memory_runtime_profile_safe(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_RUNTIME_PROFILE", "safe")
    cfg = MemoryRuntimeConfig.from_env()
    assert cfg.profile == "safe"
    assert cfg.search_concurrency >= 1
    assert cfg.dirty_dedupe_ttl_sec >= 1.0


def test_memory_runtime_env_override(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_RUNTIME_PROFILE", "balanced")
    monkeypatch.setenv("QUENTIN_MEMORY_SEARCH_CONCURRENCY", "7")
    monkeypatch.setenv("QUENTIN_MEMORY_SEARCH_TIMEOUT_S", "4.5")
    monkeypatch.setenv("QUENTIN_MEMORY_RERANK_ENABLE", "0")
    monkeypatch.setenv("QUENTIN_MEMORY_SEARCH_ADAPTIVE_DEGRADE_ENABLE", "0")
    monkeypatch.setenv("QUENTIN_MEMORY_SEARCH_TIMEOUT_PRESSURE_THRESHOLD", "0.25")
    monkeypatch.setenv("QUENTIN_MEMORY_SEARCH_ADAPTIVE_SESSION_CAP_FACTOR", "5")
    cfg = MemoryRuntimeConfig.from_env()
    assert cfg.search_concurrency == 7
    assert abs(cfg.search_timeout_s - 4.5) < 1e-6
    assert cfg.rerank_enabled is False
    assert cfg.search_adaptive_degrade_enabled is False
    assert abs(cfg.search_timeout_pressure_threshold - 0.25) < 1e-6
    assert cfg.search_adaptive_session_cap_factor == 5
