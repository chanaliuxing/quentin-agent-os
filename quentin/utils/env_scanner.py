from __future__ import annotations
import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Set, List, Optional

logger = logging.getLogger(__name__)

class EnvironmentScanner:
    """
    P5: Ported from OpenClaw's FS Fingerprinting.
    Quickly snapshots the workspace state to detect unintended side effects.
    """
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        # Atomic Detail: Ignore noise to keep scan under 100ms
        self.ignore_dirs = {".git", ".pytest_cache", "__pycache__", "venv", "logs", "data"}

    def get_workspace_fingerprint(self) -> str:
        """
        Generates a composite hash based on file paths, mtimes and sizes.
        """
        lines = []
        for root, dirs, files in os.walk(self.repo_root):
            # Prune ignored dirs in-place
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for f in files:
                full_path = Path(root) / f
                try:
                    stat = full_path.stat()
                    # We hash path + mtime + size for speed (OpenClaw Parity)
                    rel_path = full_path.relative_to(self.repo_root)
                    lines.append(f"{rel_path}:{stat.st_mtime}:{stat.st_size}")
                except (FileNotFoundError, PermissionError):
                    continue
        
        # Deterministic sort for stable hash
        lines.sort()
        payload = "\n".join(lines)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_changed_files(self, old_fingerprint_lines: List[str], new_fingerprint_lines: List[str]) -> Set[str]:
        """
        Identifies specifically which files changed.
        """
        old_set = set(old_fingerprint_lines)
        new_set = set(new_fingerprint_lines)
        diff = old_set.symmetric_difference(new_set)
        
        changed_paths = set()
        for d in diff:
            changed_paths.add(d.split(":")[0])
        return changed_paths
