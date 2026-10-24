from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class MemoryRuntimeConfig:
    profile: str = "balanced"
    # Search scheduler
    search_concurrency: int = 4
    search_timeout_s: float = 3.0
    search_overall_timeout_s: float = 0.0
    # Sync scheduler
    sync_concurrency: int = 4
    # Dirty sync
    dirty_debounce_sec: float = 5.0
    dirty_dedupe_ttl_sec: float = 120.0
    # Rerank
    rerank_enabled: bool = True
    rerank_time_half_life_hours: float = 24.0
    source_prior_session_delta: float = 0.2
    source_prior_session_file: float = 0.1
    source_prior_memory_file: float = 0.05
    domain_prior_match: float = 0.15
    search_max_sessions_scanned: int = 0
    search_max_candidates_reranked: int = 0
    search_adaptive_degrade_enabled: bool = True
    search_timeout_pressure_threshold: float = 0.4
    search_adaptive_session_cap_factor: int = 3

    @classmethod
    def from_env(cls) -> "MemoryRuntimeConfig":
        profile = str(os.getenv("QUENTIN_MEMORY_RUNTIME_PROFILE", "balanced") or "balanced").strip().lower()
        presets = {
            "safe": cls(
                profile="safe",
                search_concurrency=2,
                search_timeout_s=2.0,
                search_overall_timeout_s=4.0,
                sync_concurrency=2,
                dirty_debounce_sec=6.0,
                dirty_dedupe_ttl_sec=180.0,
                rerank_enabled=True,
                rerank_time_half_life_hours=12.0,
            ),
            "aggressive": cls(
                profile="aggressive",
                search_concurrency=8,
                search_timeout_s=5.0,
                search_overall_timeout_s=10.0,
                sync_concurrency=8,
                dirty_debounce_sec=2.0,
                dirty_dedupe_ttl_sec=60.0,
                rerank_enabled=True,
                rerank_time_half_life_hours=48.0,
            ),
            "balanced": cls(profile="balanced"),
        }
        cfg = presets.get(profile, presets["balanced"])

        def _int(name: str, cur: int) -> int:
            try:
                return int(os.getenv(name, str(cur)))
            except Exception:
                return cur

        def _float(name: str, cur: float) -> float:
            try:
                return float(os.getenv(name, str(cur)))
            except Exception:
                return cur

        cfg.search_concurrency = max(1, _int("QUENTIN_MEMORY_SEARCH_CONCURRENCY", cfg.search_concurrency))
        cfg.search_timeout_s = max(0.1, _float("QUENTIN_MEMORY_SEARCH_TIMEOUT_S", cfg.search_timeout_s))
        cfg.search_overall_timeout_s = max(0.0, _float("QUENTIN_MEMORY_SEARCH_OVERALL_TIMEOUT_S", cfg.search_overall_timeout_s))
        cfg.sync_concurrency = max(1, _int("QUENTIN_MEMORY_SYNC_CONCURRENCY", cfg.sync_concurrency))
        cfg.dirty_debounce_sec = max(0.1, _float("QUENTIN_MEMORY_DIRTY_DEBOUNCE_S", cfg.dirty_debounce_sec))
        cfg.dirty_dedupe_ttl_sec = max(1.0, _float("QUENTIN_MEMORY_DIRTY_DEDUPE_TTL_S", cfg.dirty_dedupe_ttl_sec))
        cfg.rerank_enabled = _truthy("QUENTIN_MEMORY_RERANK_ENABLE", "1" if cfg.rerank_enabled else "0")
        cfg.rerank_time_half_life_hours = max(0.1, _float("QUENTIN_MEMORY_RERANK_HALF_LIFE_HOURS", cfg.rerank_time_half_life_hours))
        cfg.source_prior_session_delta = _float("QUENTIN_MEMORY_RERANK_PRIOR_SESSION_DELTA", cfg.source_prior_session_delta)
        cfg.source_prior_session_file = _float("QUENTIN_MEMORY_RERANK_PRIOR_SESSION_FILE", cfg.source_prior_session_file)
        cfg.source_prior_memory_file = _float("QUENTIN_MEMORY_RERANK_PRIOR_MEMORY_FILE", cfg.source_prior_memory_file)
        cfg.domain_prior_match = _float("QUENTIN_MEMORY_RERANK_DOMAIN_MATCH_BONUS", cfg.domain_prior_match)
        cfg.search_max_sessions_scanned = max(0, _int("QUENTIN_MEMORY_SEARCH_MAX_SESSIONS_SCANNED", cfg.search_max_sessions_scanned))
        cfg.search_max_candidates_reranked = max(0, _int("QUENTIN_MEMORY_SEARCH_MAX_CANDIDATES_RERANKED", cfg.search_max_candidates_reranked))
        cfg.search_adaptive_degrade_enabled = _truthy(
            "QUENTIN_MEMORY_SEARCH_ADAPTIVE_DEGRADE_ENABLE",
            "1" if cfg.search_adaptive_degrade_enabled else "0",
        )
        cfg.search_timeout_pressure_threshold = max(
            0.0,
            min(1.0, _float("QUENTIN_MEMORY_SEARCH_TIMEOUT_PRESSURE_THRESHOLD", cfg.search_timeout_pressure_threshold)),
        )
        cfg.search_adaptive_session_cap_factor = max(
            1,
            _int("QUENTIN_MEMORY_SEARCH_ADAPTIVE_SESSION_CAP_FACTOR", cfg.search_adaptive_session_cap_factor),
        )
        return cfg
