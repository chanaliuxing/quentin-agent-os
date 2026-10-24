from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

class AnsiSanitizer:
    """
    P5: Ported from OpenClaw's PTY output processing.
    Strips ANSI escape codes and handles terminal control sequences.
    """
    # Pattern for all ANSI escape sequences
    ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    
    # Pattern for Device Status Report (DSR) queries
    DSR_PATTERN = re.compile(r'\x1b\[6n')

    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Removes all terminal noise to provide clean text to the LLM.
        """
        if not text:
            return ""
            
        # 1. Strip basic ANSI codes (colors, bold, etc.)
        cleaned = cls.ANSI_ESCAPE.sub('', text)
        
        # 2. Handle backspaces (e.g. progress bars often use \b)
        # Simple backspace logic: 'abc\b' -> 'ab'
        while '\b' in cleaned:
            # We use a pattern that avoids recursive issues
            new_cleaned = re.sub(r'[^\b]\b', '', cleaned, count=1)
            if new_cleaned == cleaned:
                # No more characters to delete, but \b remains at start
                cleaned = cleaned.replace('\b', '', 1)
            else:
                cleaned = new_cleaned
            
        # 3. Handle carriage returns without newlines (\r)
        # Usually used for overwriting the current line (spinners)
        # We take the last version of the line.
        lines = []
        for line in cleaned.split('\n'):
            if '\r' in line:
                # Keep only the segment after the last \r
                line = line.split('\r')[-1]
            lines.append(line)
            
        return '\n'.join(lines).strip()

    @classmethod
    def detect_dsr(cls, text: str) -> bool:
        """
        Checks if the process is asking for cursor position.
        """
        return bool(cls.DSR_PATTERN.search(text))
