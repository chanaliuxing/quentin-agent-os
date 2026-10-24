from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class CognitivePolicies:
    enable_situation_classifier: bool = True
    enable_attention_filter: bool = True
    enable_expectation_engine: bool = False
    enable_situation_to_skill: bool = False
    attention_target_ratio: float = 0.15
    prediction_error_fallback_to_planner: bool = True
    debug_use_full_context: bool = False
    enable_gist_injection: bool = True
    gist_top_k: int = 3

    @classmethod
    def load(cls, path: str | Path = "config/cognitive_policies.yaml") -> "CognitivePolicies":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8") or "") or {}
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()
        raw = data.get("cognitive_policies") if isinstance(data.get("cognitive_policies"), dict) else data
        if not isinstance(raw, dict):
            raw = {}

        def _b(k: str, default: bool) -> bool:
            v = raw.get(k, default)
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in {"1", "true", "yes", "on"}

        def _f(k: str, default: float) -> float:
            v = raw.get(k, default)
            try:
                return float(v)
            except Exception:
                return default

        def _i(k: str, default: int) -> int:
            v = raw.get(k, default)
            try:
                return int(v)
            except Exception:
                return default

        return cls(
            enable_situation_classifier=_b("enable_situation_classifier", True),
            enable_attention_filter=_b("enable_attention_filter", True),
            enable_expectation_engine=_b("enable_expectation_engine", False),
            enable_situation_to_skill=_b("enable_situation_to_skill", False),
            attention_target_ratio=max(0.01, min(0.5, _f("attention_target_ratio", 0.15))),
            prediction_error_fallback_to_planner=_b("prediction_error_fallback_to_planner", True),
            debug_use_full_context=_b("debug_use_full_context", False),
            enable_gist_injection=_b("enable_gist_injection", True),
            gist_top_k=max(0, min(10, _i("gist_top_k", 3))),
        )


def load_cognitive_policies(repo_root: str | Path = ".") -> CognitivePolicies:
    rr = Path(repo_root).resolve()
    return CognitivePolicies.load(rr / "config" / "cognitive_policies.yaml")
