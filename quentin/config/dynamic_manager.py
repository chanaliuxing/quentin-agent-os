from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

class DynamicConfigManager:
    """
    Manages AI-mutable configuration parameters (P5).
    Separates persistent environment variables from runtime-tunable knobs.
    """
    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / "config" / "auto_updatable.json"
        self._current_cache: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.config_path.exists():
            self._current_cache = {}
            return
        try:
            self._current_cache = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            self._current_cache = {}

    def get(self, key: str, default: Any = None) -> Any:
        # Priority: Env Var > Dynamic Config > Default
        env_val = os.getenv(f"QUENTIN_CFG_{key.upper()}")
        if env_val is not None:
            return env_val
        return self._current_cache.get(key, default)

    def update(self, key: str, value: Any) -> None:
        """
        AI-safe update: only allows specific keys to be modified.
        """
        allowed_keys = {
            "max_step_iterations",
            "importance_threshold",
            "no_progress_threshold",
            "enable_expectation_engine",
            "cache_ttl_sec"
        }
        if key not in allowed_keys:
            raise PermissionError(f"Configuration key '{key}' is immutable by AI.")
        
        self._current_cache[key] = value
        self._save()

    def _save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self._current_cache, indent=2), encoding="utf-8")

# Global accessor
_DYNAMIC_MANAGER: Optional[DynamicConfigManager] = None

def get_dynamic_config(repo_root: str | Path = ".") -> DynamicConfigManager:
    global _DYNAMIC_MANAGER
    if _DYNAMIC_MANAGER is None:
        _DYNAMIC_MANAGER = DynamicConfigManager(repo_root=repo_root)
    return _DYNAMIC_MANAGER
