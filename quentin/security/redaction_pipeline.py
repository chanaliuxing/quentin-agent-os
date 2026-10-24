from __future__ import annotations
import re
from typing import List, Pattern

class RedactionPipeline:
    """
    P5-B: Data Redaction Pipeline
    Redacts sensitive information from logs, traces, and memory.
    """
    def __init__(self) -> None:
        self.patterns: List[Pattern] = [
            re.compile(r"AIza[0-9A-Za-z-_]{35}"), # Google API Keys
            re.compile(r"sk-[a-zA-Z0-9]{48}"),    # OpenAI Keys
            re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), # Slack tokens
            re.compile(r"(?i)password\s*[:=]\s*[^\s,]+"), # Password fields
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[0-Z|a-z]{2,}\b"), # Emails
        ]

    def redact(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        
        redacted = text
        for pattern in self.patterns:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
