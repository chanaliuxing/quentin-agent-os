from __future__ import annotations
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TerminalDetector:
    """
    P5: Ported from OpenClaw's interaction-detector.ts.
    Identifies if a terminal process is waiting for user input.
    """
    
    # Common interactive prompts
    PROMPT_PATTERNS = [
        r"\(y/n\)\??\s*$",
        r"\[y/n\]\??\s*$",
        r"confirm\??\s*$",
        r"password:\s*$",
        r"Enter passphrase.*\s*$",
        r"Choice \[.*\]:\s*$",
        r"\?.*:$", # Generic prompt like 'Ready to proceed? :'
        r"Press \[ENTER\] to continue",
    ]

    @classmethod
    def is_waiting_for_input(cls, last_chunk: str) -> bool:
        """
        Checks the tail of the stdout buffer for interactive patterns.
        """
        if not last_chunk:
            return False
            
        # Clean ANSI and normalize
        clean_text = last_chunk.strip()
        
        for pattern in cls.PROMPT_PATTERNS:
            if re.search(pattern, clean_text, re.IGNORECASE):
                return True
        return False

    @classmethod
    def get_prompt_hint(cls, last_chunk: str) -> str:
        """
        Extracts the question being asked to help the LLM.
        """
        lines = last_chunk.splitlines()
        return lines[-1] if lines else "A prompt is waiting for your input."
