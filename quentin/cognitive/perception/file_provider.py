from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from quentin.cognitive.perception.base import PerceptionProvider

class FilePerceptionProvider(PerceptionProvider):
    """
    P5: Ported from OpenClaw's file understanding logic.
    Provides context by reading and summarizing relevant files in the workspace.
    """
    def __init__(self, repo_root: Path, max_file_chars: int = 4000):
        self.repo_root = repo_root
        self.max_file_chars = max_file_chars
        self.text_extensions = {
            ".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".tsv", 
            ".log", ".ini", ".cfg", ".conf", ".env", ".py", ".js", ".ts"
        }

    def get_perception_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts content from files mentioned in the context.
        """
        focus_paths = ctx.get("focus_paths", [])
        if not focus_paths:
            return {}

        file_contents = []
        for rel_path in focus_paths:
            full_path = self.repo_root / rel_path
            if full_path.exists() and full_path.is_file():
                ext = full_path.suffix.lower()
                if ext in self.text_extensions:
                    try:
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        if len(content) > self.max_file_chars:
                            content = content[:self.max_file_chars] + "\n...(truncated)..."
                        
                        file_contents.append({
                            "path": str(rel_path),
                            "content": content,
                            "type": "text"
                        })
                    except Exception as e:
                        file_contents.append({
                            "path": str(rel_path),
                            "error": str(e)
                        })
        
        return {"files": file_contents} if file_contents else {}
