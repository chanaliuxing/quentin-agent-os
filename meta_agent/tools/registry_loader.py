# meta_agent/tools/registry_loader.py
from __future__ import annotations
from pathlib import Path
from typing import Any, List, Optional
import json
import os
import urllib.request


def load_registry_index(path: str | Path) -> List[dict[str, Any]]:
    if str(path).startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(str(path), timeout=5) as resp:
                payload = resp.read().decode("utf-8")
            data = json.loads(payload or "[]")
            return data if isinstance(data, list) else []
        except Exception:
            return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "[]")
        if isinstance(data, list):
            return data  # type: ignore[return-value]
        return []
    except Exception:
        return []


def default_registry_index_paths() -> List[Path]:
    env_paths = os.environ.get("MCP_REGISTRY_INDEX_PATHS")
    if env_paths:
        return [Path(p) for p in env_paths.split(os.pathsep) if p]
    return [
        Path("config/mcp_registry.json"),
        Path("config/mcp/registry.json"),
        Path("data/mcp_registry.json"),
    ]


def load_first_available(paths: List[Path]) -> List[dict[str, Any]]:
    for p in paths:
        data = load_registry_index(p)
        if data:
            return data
    return []


def resolve_registry_index(registry_index: Optional[List[dict[str, Any]]], registry_index_path: Optional[str | Path]) -> List[dict[str, Any]]:
    if registry_index is not None:
        return registry_index
    if registry_index_path:
        return load_registry_index(registry_index_path)
    return load_first_available(default_registry_index_paths())
