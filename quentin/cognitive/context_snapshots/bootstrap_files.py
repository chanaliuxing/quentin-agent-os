from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging

from .base import ContextSnapshotProvider, SnapshotBlock
from quentin.infra.text.head_tail import truncate_head_tail

logger = logging.getLogger(__name__)

class BootstrapFilesProvider(ContextSnapshotProvider):
    """
    P5 Port: Bootstrap Files (Anchor Files).
    Ensures critical project context is ALWAYS available in the snapshot.
    """
    @property
    def id(self) -> str:
        return "bootstrap_files"

    @property
    def priority(self) -> int:
        return 100  # High priority, we want these anchors at the top

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]:
        # Anchor list
        anchors = [
            "AGENTS.md",
            "TODO_TAYLOR_EVOLUTION.md",
            "quentin/mutable/HEARTBEAT.md",
            "README.md",
            "blueprint.md"
        ]
        
        # Also try to find tool manifests if relevant
        task_input = str(context.get("task_input", "")).lower()
        if "tool" in task_input or "extension" in task_input or "gemini" in task_input:
            # Quick scan for manifests (limited to avoid slow IO)
            try:
                for p in (repo_root / "extensions/tools").glob("**/manifest.yaml"):
                    anchors.append(str(p.relative_to(repo_root)))
                for p in (repo_root / "extensions/tools").glob("**/manifest.yml"):
                    anchors.append(str(p.relative_to(repo_root)))
            except Exception:
                pass

        lines = []
        for rel_path in anchors:
            full_path = repo_root / rel_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    # Apply Head/Tail truncation (12k chars default)
                    safe_content = truncate_head_tail(content, max_chars=8000)
                    lines.append(f"--- FILE: {rel_path} ---")
                    lines.append(safe_content)
                    lines.append("-" * 30)
                except Exception as e:
                    logger.warning(f"BootstrapFilesProvider: Failed to read {rel_path}: {e}")

        if not lines:
            return None

        content = "\n".join(lines)
        return SnapshotBlock(
            id=self.id,
            title="Bootstrap Anchor Files",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            meta={"anchors_read": len(lines) // 3}
        )
