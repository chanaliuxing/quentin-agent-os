from __future__ import annotations
import difflib
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

class FuzzyMatcher:
    """
    P5: Ported from OpenClaw's self-healing patch logic.
    Finds near-miss matches in a file to help Agent correct its 'oldText'.
    """
    
    @staticmethod
    def find_near_match(content: str, search_text: str, threshold: float = 0.7) -> Optional[Tuple[str, int]]:
        """
        Scans content for a block similar to search_text.
        Returns (best_match_text, start_line_index) or None.
        """
        search_lines = search_text.splitlines()
        content_lines = content.splitlines()
        
        if not search_lines or not content_lines:
            return None
            
        best_ratio = 0.0
        best_match = None
        best_idx = -1
        
        # Sliding window approach (OpenClaw Parity)
        window_size = len(search_lines)
        for i in range(len(content_lines) - window_size + 1):
            window_content = "\n".join(content_lines[i : i + window_size])
            ratio = difflib.SequenceMatcher(None, window_content, search_text).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = window_content
                best_idx = i
                
        if best_ratio >= threshold:
            logger.info(f"FuzzyMatcher: Found candidate with ratio {best_ratio:.2f} at line {best_idx + 1}")
            return best_match, best_idx
            
        return None

    @staticmethod
    def get_whitespace_agnostic_match(content: str, search_text: str) -> Optional[str]:
        """
        Attempts to match by ignoring all whitespace.
        """
        def clean(s: str) -> str:
            return "".join(s.split())
            
        clean_search = clean(search_text)
        content_lines = content.splitlines()
        window_size = len(search_text.splitlines())
        
        for i in range(len(content_lines) - window_size + 1):
            window_content = "\n".join(content_lines[i : i + window_size])
            if clean(window_content) == clean_search:
                return window_content
        return None
