from __future__ import annotations
from .base import BaseCompactor, CompactionResult

class TruncateCompactor(BaseCompactor):
    def compact(self, text: str, target_chars: int) -> CompactionResult:
        original = len(text)
        if original <= target_chars:
            return CompactionResult(text, original, original, "none")
            
        keep = target_chars // 2
        head = text[:keep]
        tail = text[-keep:]
        compacted = f"{head}\n...[Truncated {original - target_chars} chars]...\n{tail}"
        
        return CompactionResult(compacted, original, len(compacted), "truncate")
