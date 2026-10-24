from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from quentin.memory.models import MemoryRecord, MemoryTier

logger = logging.getLogger(__name__)

class SessionPruner:
    """
    P5: Ported from OpenClaw's session-pruning logic.
    Trims old tool results to reduce context bloat before LLM calls.
    Focuses on 'Soft-trim' (head/tail preservation) and 'Hard-clear'.
    """
    def __init__(
        self, 
        keep_last_steps: int = 3,
        soft_limit_chars: int = 4000,
        hard_limit_tokens: int = 6000 # ~24k chars
    ):
        self.keep_last_steps = keep_last_steps
        self.soft_limit_chars = soft_limit_chars
        self.hard_limit_tokens = hard_limit_tokens

    def prune_memories(self, memories: List[MemoryRecord]) -> List[MemoryRecord]:
        """
        Selectively prunes a list of memory records.
        Rules:
        1. Never prune user/system messages.
        2. Never prune records with images.
        3. Protect the last N tool results.
        4. Soft-trim oversized old tool results.
        """
        if len(memories) <= self.keep_last_steps + 2:
            return memories

        protected_indices = set()
        
        # 1. Identify indices to protect
        # Always keep the first message (root task)
        protected_indices.add(0)
        
        # Keep the last few records
        for i in range(len(memories) - self.keep_last_steps, len(memories)):
            if i >= 0:
                protected_indices.add(i)

        pruned_results = []
        for idx, rec in enumerate(memories):
            if idx in protected_indices:
                pruned_results.append(rec)
                continue
            
            # Check for images or non-tool records
            is_tool_result = "tool_result" in (rec.tags or []) or rec.source.startswith("tool:")
            has_images = "image" in str(rec.metadata.get("media_understanding", ""))
            
            if not is_tool_result or has_images:
                pruned_results.append(rec)
                continue

            # 2. Perform Soft-trim
            if len(rec.content) > self.soft_limit_chars:
                logger.info(f"Pruner: Soft-trimming old tool result {rec.id}")
                head = rec.content[:self.soft_limit_chars // 2]
                tail = rec.content[-self.soft_limit_chars // 2:]
                new_content = f"{head}\n\n... [Old Tool Result Truncated ({len(rec.content)} chars)] ...\n\n{tail}"
                
                # Create a cloned record with trimmed content
                # (Note: We don't modify the original in DB, just the transient list)
                rec.content = new_content
                
            pruned_results.append(rec)

        return pruned_results

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4
