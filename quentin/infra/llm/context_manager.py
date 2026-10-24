from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ContextBudgetManager:
    """
    Manages LLM context windows and proactive compaction.
    Aligned with OpenClaw's context-window-guard.
    """
    def __init__(self, limit: int = 128000, threshold: float = 0.8):
        self.limit = limit
        self.threshold = threshold
        self.current_tokens = 0

    def record_usage(self, tokens: int):
        self.current_tokens += tokens
        usage_ratio = self.current_tokens / self.limit
        if usage_ratio > self.threshold:
            logger.warning(f"Context budget nearing limit: {usage_ratio:.1%} ({self.current_tokens}/{self.limit})")

    def should_flush(self) -> bool:
        """Returns True if a proactive memory flush/summary is needed."""
        return (self.current_tokens / self.limit) > self.threshold

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (approx 4 chars per token)."""
        return len(text) // 4

    def reset(self):
        self.current_tokens = 0

# Instance can be per-session
