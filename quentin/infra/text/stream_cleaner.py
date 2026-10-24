from __future__ import annotations
import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

class StreamCleaner:
    """
    P5: Ported from OpenClaw's response formatter.
    Cleans LLM stream residue and ensures UI-friendly Markdown.
    """
    def __init__(self):
        self.buffer = ""
        self.output_pointer = 0
        self.in_thought_block = False
        self.code_block_count = 0

    def process_token(self, token: str) -> str:
        """
        Processes a raw token and returns the 'safe' version for the UI.
        """
        self.buffer += token
        
        # 1. Thought Block Stripping (OpenClaw Parity)
        # We search for tags like <thought> or [[thought]] and suppress them
        # Simplified: regex-based suppression on the growing buffer
        
        # 2. Code Block Tracking
        if "```" in token:
            self.code_block_count += 1
            
        # 3. Delta Extraction
        # We only return the newly added safe characters
        full_visible = self._get_visible_text(self.buffer)
        delta = full_visible[self.output_pointer:]
        self.output_pointer = len(full_visible)
        
        return delta

    def _get_visible_text(self, raw: str) -> str:
        """
        Physically strips non-user content like thought blocks.
        """
        # Strip <thought>...</thought>
        cleaned = re.sub(r'<thought>.*?</thought>', '', raw, flags=re.DOTALL)
        # Strip currently open thought tags
        cleaned = re.sub(r'<thought>.*$', '', cleaned, flags=re.DOTALL)
        return cleaned

    def finalize(self) -> str:
        """
        Auto-closes unclosed Markdown tags at the end of the stream.
        """
        final_patch = ""
        if self.code_block_count % 2 != 0:
            final_patch += "\n```"
        return final_patch
