from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import subprocess

from quentin.cognitive.context_snapshots.base import ContextSnapshotProvider, SnapshotBlock

class FileTreeSnapshotProvider(ContextSnapshotProvider):
    """
    Provides a bounded file tree of the workspace.
    """
    @property
    def id(self) -> str:
        return "file_tree"

    @property
    def priority(self) -> int:
        return 100

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]:
        max_depth = int(os.getenv("QUENTIN_SNAPSHOT_TREE_DEPTH", "2"))
        max_files = int(os.getenv("QUENTIN_SNAPSHOT_TREE_MAX_FILES", "100"))
        
        # Use 'find' or 'ls -R' for portability, or just walk with python
        tree_lines: List[str] = []
        count = 0
        
        def walk(current_dir: Path, depth: int):
            nonlocal count
            if depth > max_depth or count >= max_files:
                return
            
            try:
                # Filter out hidden dirs and common noise
                entries = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name))
                for entry in entries:
                    if count >= max_files:
                        break
                    if entry.name.startswith(".") and entry.name != ".gitignore":
                        continue
                    if entry.name in ("__pycache__", "node_modules", "venv", ".git"):
                        continue
                        
                    rel = entry.relative_to(repo_root)
                    prefix = "  " * (depth - 1)
                    if entry.is_dir():
                        tree_lines.append(f"{prefix}{entry.name}/")
                        walk(entry, depth + 1)
                    else:
                        tree_lines.append(f"{prefix}{entry.name}")
                        count += 1
            except PermissionError:
                pass

        walk(repo_root, 1)
        
        if not tree_lines:
            return None
            
        content = "\n".join(tree_lines)
        return SnapshotBlock(
            id=self.id,
            title="Workspace File Tree (Bounded)",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            meta={"depth": max_depth, "files_count": count}
        )
