from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import List, Optional, Set
from pydantic import BaseModel

logger = logging.getLogger(__name__)

AUTO_UPDATABLE_MARKERS = (
    "AUTO_UPDATABLE: true",
    "AUTO_UPDATABLE=true",
    "AUTO_UPDATABLE",
    "@auto_updatable",
)

class AutoUpdatableConfig(BaseModel):
    require_marker: bool = True
    paths: List[str] = []
    # P2: 允许特定路径自动注入标记
    # Default is empty to keep safety strict unless explicitly enabled by config.
    auto_inject_paths: List[str] = []

def load_auto_updatable_config(repo_root: str | Path) -> AutoUpdatableConfig:
    import json
    path = Path(repo_root) / "config" / "auto_updatable.json"
    if not path.exists():
        return AutoUpdatableConfig()
    try:
        return AutoUpdatableConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to load auto_updatable.json: {e}")
        return AutoUpdatableConfig()

def is_file_marked_auto_updatable(file_path: Path) -> bool:
    if not file_path.exists():
        return False
    try:
        # Check first 20 lines for marker
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                if any(m in line for m in AUTO_UPDATABLE_MARKERS):
                    return True
    except Exception:
        return False
    return False

def inject_auto_updatable_marker(file_path: Path) -> bool:
    """
    Injects the @auto_updatable marker into the file header.
    """
    if not file_path.exists():
        return False
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        marker = "# @auto_updatable\n"
        if file_path.suffix == ".py" or file_path.suffix in (".yaml", ".yml", ".md"):
            # Check if it already has something similar to avoid double injection if is_file_marked_auto_updatable failed
            if any(m in content[:500] for m in AUTO_UPDATABLE_MARKERS):
                return True
            file_path.write_text(marker + content, encoding="utf-8")
            logger.info(f"Injected auto_updatable marker into {file_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to inject marker into {file_path}: {e}")
    return False

def ensure_auto_updatable(*, repo_root: str | Path, rel_path: str, allow_auto_inject: bool = True) -> None:
    root = Path(repo_root).resolve()
    target = (root / rel_path).resolve()
    rel_clean = str(target.relative_to(root))
    
    cfg = load_auto_updatable_config(root)
    
    # 1. Check allowlist paths
    is_allowed_path = False
    for p in cfg.paths:
        if rel_clean.startswith(p.strip("/")):
            is_allowed_path = True
            break
    
    # 2. Check markers if required
    if cfg.require_marker:
        if not is_file_marked_auto_updatable(target):
            # P2: 如果在 auto_inject_paths 中，自动注入
            should_inject = False
            for p in cfg.auto_inject_paths:
                if rel_clean.startswith(p.strip("/")):
                    should_inject = True
                    break
            
            if should_inject and allow_auto_inject:
                if inject_auto_updatable_marker(target):
                    return
            
            raise ValueError(f"file is not auto_updatable (missing marker): {rel_clean}")
    elif not is_allowed_path:
        raise ValueError(f"file is not auto_updatable (not allowlisted): {rel_clean}")
