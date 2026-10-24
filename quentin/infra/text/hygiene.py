from __future__ import annotations

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class TranscriptHygiene:
    """
    P5: Ported from OpenClaw's pi-embedded-helpers/errors.ts.
    Detects and prevents LLM from repeating history or redundant blocks.
    """
    @staticmethod
    def collapse_duplicates(text: str) -> str:
        """
        Collapses consecutive duplicate blocks of text.
        """
        if not text or len(text) < 50:
            return text
            
        blocks = re.split(r"\n{2,}", text.strip())
        if len(blocks) < 2:
            return text
            
        def normalize(s: str) -> str:
            return re.sub(r"\s+", " ", s.strip()).lower()
            
        result = []
        last_norm = None
        
        for b in blocks:
            norm = normalize(b)
            if last_norm and norm == last_norm:
                logger.warning("Hygiene: Detected redundant block repetition. Collapsing.")
                continue
            result.append(b.strip())
            last_norm = norm
            
        return "\n\n".join(result)

    @staticmethod
    def detect_history_leak(current_output: str, history: List[str]) -> bool:
        """
        Checks if the model is leaking/re-generating old messages.
        """
        if len(current_output) < 100:
            return False
            
        norm_output = current_output.strip().lower()
        for h in history:
            if not h: continue
            norm_h = h.strip().lower()
            # If output contains a long segment of a previous message
            if len(norm_h) > 50 and norm_h in norm_output:
                return True
        return False
