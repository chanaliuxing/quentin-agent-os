from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImmuneLoopDefaults:
    """
    Stable defaults for `quentin.loops.immune_loop.ImmuneLoop`.

    This file-backed config is intentionally conservative:
    - It only covers thresholds / sampling knobs that are safe to A/B and promote.
    - It does NOT enable self-fix by itself.
    """

    window_minutes: Optional[int] = None
    min_samples: Optional[int] = None
    error_rate_threshold: Optional[float] = None
    latency_ms_threshold: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImmuneLoopDefaults":
        d = dict(data or {})
        return cls(
            window_minutes=int(d["window_minutes"]) if d.get("window_minutes") is not None else None,
            min_samples=int(d["min_samples"]) if d.get("min_samples") is not None else None,
            error_rate_threshold=float(d["error_rate_threshold"]) if d.get("error_rate_threshold") is not None else None,
            latency_ms_threshold=float(d["latency_ms_threshold"]) if d.get("latency_ms_threshold") is not None else None,
        )


def load_immune_loop_defaults(path: str | Path) -> Optional[ImmuneLoopDefaults]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        logger.exception("Failed to parse immune loop defaults: %s", p)
        return None

    if isinstance(raw, dict) and isinstance(raw.get("defaults"), dict):
        raw = raw["defaults"]
    if not isinstance(raw, dict):
        return None
    try:
        return ImmuneLoopDefaults.from_dict(raw)
    except Exception:
        logger.exception("Invalid immune loop defaults schema: %s", p)
        return None

