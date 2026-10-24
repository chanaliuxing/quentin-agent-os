from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class MCPSecurityConfig:
    enabled: bool = False
    allow_auto_tool_install: bool = False
    official_scopes: List[str] = field(default_factory=list)
    whitelist: List[str] = field(default_factory=list)
    dangerous_categories: List[str] = field(default_factory=lambda: ["filesystem", "shell", "browser"])
    enable_tool_governance: bool = False
    tool_governance_council: str = "tool_governance"
    enable_tool_learning: bool = False
    tool_learning_max_examples: int = 2

    @classmethod
    def load(cls, path: str | Path = "config/mcp_security.yaml") -> "MCPSecurityConfig":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8") or "") or {}
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()
        raw = data.get("mcp_security") if isinstance(data.get("mcp_security"), dict) else data
        if not isinstance(raw, dict):
            raw = {}

        def _b(key: str, default: bool) -> bool:
            v = raw.get(key, default)
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in {"1", "true", "yes", "on"}

        def _lst(key: str, default: List[str]) -> List[str]:
            v = raw.get(key)
            if isinstance(v, list):
                out: List[str] = []
                for item in v:
                    s = str(item or "").strip()
                    if s:
                        out.append(s)
                return out
            return list(default)

        def _i(key: str, default: int) -> int:
            v = raw.get(key, default)
            try:
                return int(v)
            except Exception:
                return default

        return cls(
            enabled=_b("enabled", False),
            allow_auto_tool_install=_b("allow_auto_tool_install", False),
            official_scopes=_lst("official_scopes", []),
            whitelist=_lst("whitelist", []),
            dangerous_categories=_lst("dangerous_categories", ["filesystem", "shell", "browser"]),
            enable_tool_governance=_b("enable_tool_governance", False),
            tool_governance_council=str(raw.get("tool_governance_council") or "tool_governance").strip()
            or "tool_governance",
            enable_tool_learning=_b("enable_tool_learning", False),
            tool_learning_max_examples=max(0, min(10, _i("tool_learning_max_examples", 2))),
        )


def load_mcp_security(repo_root: str | Path = ".") -> MCPSecurityConfig:
    rr = Path(repo_root).resolve()
    return MCPSecurityConfig.load(rr / "config" / "mcp_security.yaml")
