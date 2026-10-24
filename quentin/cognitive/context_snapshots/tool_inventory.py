from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from quentin.cognitive.context_snapshots.base import ContextSnapshotProvider, SnapshotBlock

class ToolInventorySnapshotProvider(ContextSnapshotProvider):
    """
    Provides a summary of available tools.
    """
    @property
    def id(self) -> str:
        return "tool_inventory"

    @property
    def priority(self) -> int:
        return 90

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]:
        # Try to get tools from context or global ToolManager if available
        # This is a bit tricky as ToolManager might not be easily accessible here.
        # We can at least list the builtin categories or common tools.
        
        # If the executor passed tool summaries in context, use them.
        tool_summaries = context.get("tool_summaries")
        if isinstance(tool_summaries, dict):
            content_lines = []
            for name, desc in tool_summaries.items():
                content_lines.append(f"- {name}: {desc}")
            content = "\n".join(content_lines)
            return SnapshotBlock(
                id=self.id,
                title="Available Tools Inventory",
                content=content,
                size_bytes=len(content.encode("utf-8"))
            )
            
        return None
