from __future__ import annotations
import logging
import os
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class BudgetGuard:
    """
    P5: Ported from OpenClaw's turn-level budget guard.
    Prevents expensive operations by predicting or checking turn costs.
    """
    def __init__(self):
        # 1. Configurable limits (OpenClaw Parity)
        self.max_tokens_per_turn = int(os.getenv("QUENTIN_MAX_TOKENS_PER_TURN", "32000"))
        self.max_usd_per_task = float(os.getenv("QUENTIN_MAX_USD_PER_TASK", "5.0"))
        
    def check_result_payload(self, content: str) -> Tuple[bool, str]:
        """
        Checks if a tool result is too large for a single turn.
        Returns (is_allowed, reason)
        """
        # Roughly 4 chars per token
        est_tokens = len(content) // 4
        
        if est_tokens > self.max_tokens_per_turn:
            return False, f"Turn budget exceeded: payload has {est_tokens} tokens, max is {self.max_tokens_per_turn}."
            
        return True, ""

    def should_halt_task(self, total_usd: float) -> bool:
        """
        Hard kill if the entire task is getting too expensive.
        """
        return total_usd > self.max_usd_per_task
