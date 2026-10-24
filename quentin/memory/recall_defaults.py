from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryRecallDefaults:
    """
    Stable defaults for MemoryFabric.recall when query.mode == "auto".

    This is intentionally simple and file-backed so L3 promotions can apply offline.
    """

    mode: str = "auto"  # auto | vector_only | text_only | hybrid
    alpha: float = 0.5
    k_text: Optional[int] = None
    k_vec: Optional[int] = None
    min_text_score: float = 0.0
    min_vec_score: float = 0.0
    text_mode: Optional[str] = None  # like | fts

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecallDefaults":
        d = dict(data or {})
        return cls(
            mode=str(d.get("mode") or "auto"),
            alpha=float(d.get("alpha") if d.get("alpha") is not None else 0.5),
            k_text=int(d["k_text"]) if d.get("k_text") is not None else None,
            k_vec=int(d["k_vec"]) if d.get("k_vec") is not None else None,
            min_text_score=float(d.get("min_text_score") or 0.0),
            min_vec_score=float(d.get("min_vec_score") or 0.0),
            text_mode=str(d["text_mode"]) if d.get("text_mode") is not None else None,
        )


def load_memory_recall_defaults(path: str | Path) -> Optional[MemoryRecallDefaults]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        logger.exception("Failed to parse memory recall defaults: %s", p)
        return None

    if isinstance(raw, dict) and isinstance(raw.get("defaults"), dict):
        raw = raw["defaults"]
    if not isinstance(raw, dict):
        return None
    try:
        return MemoryRecallDefaults.from_dict(raw)
    except Exception:
        logger.exception("Invalid memory recall defaults schema: %s", p)
        return None

