from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
import os

from quentin.cognitive.context_snapshots.base import ContextSnapshotProvider, SnapshotBlock

class GitStatusSnapshotProvider(ContextSnapshotProvider):
    """
    Provides a summary of current git status.
    """
    @property
    def id(self) -> str:
        return "git_status"

    @property
    def priority(self) -> int:
        return 80

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]:
        if not (repo_root / ".git").exists():
            return None
            
        try:
            # Get short porcelain status
            res = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode != 0:
                return None
                
            content = res.stdout.strip()
            if not content:
                return None
                
            return SnapshotBlock(
                id=self.id,
                title="Git Status Summary",
                content=content,
                size_bytes=len(content.encode("utf-8"))
            )
        except Exception:
            return None
