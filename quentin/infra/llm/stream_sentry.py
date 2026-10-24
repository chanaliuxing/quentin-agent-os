from __future__ import annotations
import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class StreamSentry:
    """
    P5: Ported from OpenClaw's repetition-detection.ts.
    Monitors LLM token stream for redundancy and structure errors.
    """
    def __init__(self, history_snippets: List[str] = None):
        self.buffer = ""
        self.history_snippets = history_snippets or []
        self.repetition_threshold = 60 # chars
        
    def push_and_check(self, token: str) -> Optional[str]:
        """
        Pushes a new token and checks for intervention needs.
        Returns error reason if intervention is needed, else None.
        """
        self.buffer += token
        
        # 1. Self-Repetition Check (Glitch detection)
        # Look for repeating sub-patterns like "abcabcabc"
        if len(self.buffer) > self.repetition_threshold * 2:
            # Check last 100 chars for pattern like (....)\1{2,}
            tail = self.buffer[-100:]
            for length in range(10, 40):
                pattern = tail[-length:]
                if tail.count(pattern) >= 3:
                    return "self_repetition_detected"

        # 2. History Leakage Check
        # Check if the model is repeating the system prompt or user history word-for-word
        for snippet in self.history_snippets:
            if len(snippet) > self.repetition_threshold:
                if snippet in self.buffer:
                    return "history_leakage_detected"

        # 3. Structural Malformation
        # If it's supposed to be JSON but starts with lots of text
        if len(self.buffer) > 200 and not any(c in self.buffer[:50] for c in "{["):
            # This is a soft heuristic, might need domain tuning
            pass
            
        return None

    def get_clean_buffer(self) -> str:
        return self.buffer
