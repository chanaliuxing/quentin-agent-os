from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Set

logger = logging.getLogger(__name__)


def _norm_bool(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _norm_bool(raw)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return str(default)
    return str(raw)


def env_csv(name: str, default: Optional[Sequence[str]] = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default or [])
    parts = [p.strip() for p in str(raw).split(",")]
    return [p for p in parts if p]


@dataclass(frozen=True)
class LegacyEnvMapping:
    legacy: str
    canonical: str
    # When True, always overwrite canonical from legacy. Keep False by default.
    force: bool = False


class EnvManager:
    """
    Tier 0 environment normalizer (OpenClaw parity).

    Goals:
    - Provide consistent parsing helpers (bool/int/float/csv).
    - Provide explicit legacy env var mappings (back-compat).
    - Avoid side effects at import time; normalization is opt-in (Container calls it).
    """

    def __init__(self) -> None:
        self._logged_vars: Set[str] = set()

    def normalize(self, *, mappings: Optional[Iterable[LegacyEnvMapping]] = None) -> None:
        # Safe legacy mappings for known drift.
        default_mappings = [
            LegacyEnvMapping("Z_AI_API_KEY", "ZAI_API_KEY"),
        ]
        for m in list(mappings or []) + default_mappings:
            self._apply_mapping(m)

        # Special-case: QUENTIN_ROUTING_POLICY_PLUGINS is a boolean enable flag, not an id.
        # If it is enabled and QUENTIN_ROUTING_POLICY is empty, set it to "default".
        if env_bool("QUENTIN_ROUTING_POLICY_PLUGINS", False):
            if not (os.getenv("QUENTIN_ROUTING_POLICY") or "").strip():
                os.environ["QUENTIN_ROUTING_POLICY"] = "default"

    def _apply_mapping(self, m: LegacyEnvMapping) -> None:
        legacy = (m.legacy or "").strip()
        canonical = (m.canonical or "").strip()
        if not legacy or not canonical:
            return
        if legacy not in os.environ:
            return
        if canonical in os.environ and not m.force:
            return
        os.environ[canonical] = os.environ[legacy]

    def log_option(self, key: str, *, redact: bool = False) -> None:
        if key in self._logged_vars:
            return
        val = os.getenv(key)
        if val is None:
            return
        display_val = "******" if redact else val
        logger.info("ENV: %s=%s", key, display_val)
        self._logged_vars.add(key)


env_manager = EnvManager()


__all__ = [
    "env_manager",
    "env_bool",
    "env_int",
    "env_float",
    "env_str",
    "env_csv",
    "LegacyEnvMapping",
]
