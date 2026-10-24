from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class Constitution:
    """
    Constitution is a human-authored governance policy document.

    This is intentionally lightweight: it loads structured rules from `governance.yaml`
    (repo root by default) and exposes the raw policy for other components (SafetyKernel,
    councils, experiment policies).
    """

    policy: Dict[str, Any]
    source_path: str

    @classmethod
    def load(cls, path: str | Path = "governance.yaml") -> "Constitution":
        p = Path(path)
        if not p.exists():
            return cls(policy={}, source_path=str(p))
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {"raw": data}
        return cls(policy=data, source_path=str(p))

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.policy.get(key, default)

