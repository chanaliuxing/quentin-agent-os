from __future__ import annotations
import re
import hashlib
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class StreamUtils:
    """
    P5: Ported from OpenClaw's stream-hashing logic.
    Identifies and collapses repetitive terminal progress lines.
    """
    
    # Matches numbers, percentages, and common progress bar chars
    PROGRESS_PATTERN = re.compile(r'\d+(\.\d+)?%?|\[[=#-]*\]')

    @classmethod
    def get_semantic_hash(cls, line: str) -> str:
        """
        Strips dynamic progress data and returns a hash of the stable part.
        Example: "Downloading package A: 45%" -> "Downloading package A: " -> hash
        """
        # 1. Normalize line (strip whitespace and ANSI is assumed already handled)
        clean_line = line.strip()
        
        # 2. Strip dynamic numbers and bars
        stable_part = cls.PROGRESS_PATTERN.sub('', clean_line)
        
        # 3. Compute Hash
        return hashlib.md5(stable_part.encode("utf-8")).hexdigest()

    @classmethod
    def should_collapse(cls, last_hash: Optional[str], current_hash: str) -> bool:
        """
        True if the current line is just a progress update of the last one.
        """
        return last_hash == current_hash
