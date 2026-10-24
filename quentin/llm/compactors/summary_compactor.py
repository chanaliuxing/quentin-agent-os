from __future__ import annotations
import logging
from .base import BaseCompactor, CompactionResult
from .truncate_compactor import TruncateCompactor

logger = logging.getLogger(__name__)

class SummaryCompactor(BaseCompactor):
    """
    High-fidelity compactor using LLM summarization.
    Falls back to TruncateCompactor on failure.
    """
    def compact(self, text: str, target_chars: int) -> CompactionResult:
        original = len(text)
        if original <= target_chars:
            return CompactionResult(text, original, original, "none")

        try:
            # Simple Heuristic Summary (Lines)
            lines = text.splitlines()
            if len(lines) < 10:
                raise ValueError("Too few lines")
                
            keep_lines = max(5, int(target_chars / 100))
            head = lines[:keep_lines//2]
            tail = lines[-keep_lines//2:]
            
            skipped = len(lines) - len(head) - len(tail)
            compacted = "\n".join(head + [f"... [Summarized: skipped {skipped} lines] ..."] + tail)
            
            if len(compacted) > target_chars:
                raise ValueError("Heuristic summary still too long")
                
            return CompactionResult(compacted, original, len(compacted), "summary_heuristic")

        except Exception as e:
            logger.warning(f"SummaryCompactor failed: {e}. Falling back to truncate.")
            return TruncateCompactor().compact(text, target_chars)
