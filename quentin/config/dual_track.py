from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass(frozen=True)
class DualTrackConfig:
    enabled: bool = False
    allow_in_staging: bool = False
    allow_in_prod: bool = False
    blocked_domains: List[str] = field(default_factory=lambda: ["legal", "trading"])
    require_tool_governance: bool = True
    require_patch_governance: bool = True
    max_requests_per_attempt: int = 2

    @classmethod
    def load(cls, path: str | Path = "config/dual_track.yaml") -> "DualTrackConfig":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8") or "") or {}
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()
        raw = data.get("dual_track") if isinstance(data.get("dual_track"), dict) else data
        if not isinstance(raw, dict):
            raw = {}

        def _b(k: str, default: bool) -> bool:
            v = raw.get(k, default)
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in {"1", "true", "yes", "on"}

        def _i(k: str, default: int) -> int:
            v = raw.get(k, default)
            try:
                return int(v)
            except Exception:
                return default

        def _lst(k: str, default: List[str]) -> List[str]:
            v = raw.get(k)
            if isinstance(v, list):
                out: List[str] = []
                for item in v:
                    s = str(item or "").strip()
                    if s:
                        out.append(s)
                return out
            return list(default)

        return cls(
            enabled=_b("enabled", False),
            allow_in_staging=_b("allow_in_staging", False),
            allow_in_prod=_b("allow_in_prod", False),
            blocked_domains=_lst("blocked_domains", ["legal", "trading"]),
            require_tool_governance=_b("require_tool_governance", True),
            require_patch_governance=_b("require_patch_governance", True),
            max_requests_per_attempt=max(0, min(10, _i("max_requests_per_attempt", 2))),
        )


def load_dual_track_config(repo_root: str | Path = ".") -> DualTrackConfig:
    rr = Path(repo_root).resolve()
    return DualTrackConfig.load(rr / "config" / "dual_track.yaml")

