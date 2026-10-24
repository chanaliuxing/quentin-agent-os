from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


class MemoryExporter:
    """Export memory entries to human-readable Markdown files."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.export_dir = self.repo_root / "data" / "memory" / "human_readable"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_entry(self, entry: Any) -> Path:
        """Convert a MemoryEntry-like object to a Markdown file."""
        try:
            eid = getattr(entry, "id", "unknown")
            tier_obj = getattr(entry, "tier", "STS")
            tier = getattr(tier_obj, "value", str(tier_obj))
            source = getattr(entry, "source", "unknown")
            content = getattr(entry, "content", "")
            tags = getattr(entry, "tags", [])
            created_at = getattr(entry, "created_at", now_iso())

            filename = f"{tier}_{str(eid)[:8]}.md"
            target_path = self.export_dir / filename

            md_content = "\n".join(
                [
                    f"# Memory Entry: {eid}",
                    "",
                    "**Metadata:**",
                    f"- **Tier:** {tier}",
                    f"- **Source:** {source}",
                    f"- **Created At:** {created_at}",
                    f"- **Tags:** {', '.join(tags) if tags else 'None'}",
                    "",
                    "---",
                    "",
                    "## Content",
                    "",
                    str(content),
                    "",
                    "---",
                    "",
                    "*Auto-exported by Quentin MemoryFabric*",
                ]
            )

            target_path.write_text(md_content, encoding="utf-8")
            return target_path
        except Exception as e:
            logger.error("MemoryExporter: Failed to export entry %s: %s", getattr(entry, "id", "?"), e)
            return Path()


def get_memory_exporter(repo_root: str | Path = ".") -> MemoryExporter:
    return MemoryExporter(repo_root=repo_root)
