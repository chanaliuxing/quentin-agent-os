from __future__ import annotations
from typing import Dict, Any, List
import logging
from quentin.llm.context_budget import apply_context_budget, ContextWindowGuardResult

logger = logging.getLogger(__name__)

class ContextGuard:
    """
    Tier 0 Context Window Guard (Adapter).
    Delegates to the unified quentin.llm.context_budget logic.
    """
    def __init__(self, limit: int = 8192, warn_threshold: float = 0.8):
        self.limit = limit
        self.warn_threshold = warn_threshold

    def check(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Returns {'safe': bool, 'usage': int, 'action': 'none' | 'compact' | 'fail'}
        """
        # Convert messages to text for budget check
        prompt_text = "\n".join([str(m.get("content", "")) for m in messages])
        
        # Use the unified API
        # warn_threshold 0.8 -> reserve 20%
        reserve = int(self.limit * (1.0 - self.warn_threshold))
        
        _, guard = apply_context_budget(
            prompt_text=prompt_text,
            context_window_tokens=self.limit,
            reserve_tokens=reserve,
            auto_compact=False # We handle action return, not auto-mutation here
        )
        
        if guard.should_block:
            if guard.reason == "context_overflow":
                return {"safe": False, "usage": guard.total_tokens, "action": "fail"}
            if guard.reason == "context_near_overflow":
                return {"safe": True, "usage": guard.total_tokens, "action": "compact"}
        
        return {"safe": True, "usage": guard.total_tokens, "action": "none"}

    def compact_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Naive compaction: Keep system prompt + last 4 messages.
        Summarize the middle.
        """
        if len(messages) <= 5:
            return messages
            
        system = [m for m in messages if m["role"] == "system"]
        others = [m for m in messages if m["role"] != "system"]
        
        if len(others) <= 4:
            return messages
            
        # Keep last 4
        kept = others[-4:]
        
        # Insert summary placeholder
        summary_msg = {
            "role": "system",
            "content": f"[System: Previous {len(others) - 4} messages were compacted to save memory.]"
        }
        
        return system + [summary_msg] + kept
