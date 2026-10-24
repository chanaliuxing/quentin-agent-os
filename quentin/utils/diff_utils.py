from __future__ import annotations
import difflib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DiffUtils:
    """
    P5: Ported from OpenClaw's action-delta tracking.
    Generates clean Unified Diffs for memory indexing.
    """
    @staticmethod
    def get_unified_diff(old_text: str, new_text: str, filename: str) -> Optional[str]:
        """
        Produces a standard unified diff string.
        """
        if old_text == new_text:
            return None
            
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=3 # Context lines
        )
        
        diff_text = "".join(diff).strip()
        return diff_text if diff_text else None

    @staticmethod
    def format_as_memory(filename: str, diff: str) -> str:
        """
        Formats the diff into a semantic narrative for better LLM retrieval.
        """
        return f"ACTION RECALL: I modified '{filename}'. The specific changes are:\n\n```diff\n{diff}\n```"
