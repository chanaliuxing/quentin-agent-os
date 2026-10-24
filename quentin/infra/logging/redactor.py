from __future__ import annotations

import re
import os
import getpass
from typing import List

class DeepRedactor:
    """
    Comprehensive PII (Personally Identifiable Information) Redactor.
    Matches OpenClaw's logging/log-redaction.ts.
    """
    def __init__(self):
        self.username = getpass.getuser()
        self.patterns = [
            # 1. API Keys (Existing logic)
            (r"sk-[a-zA-Z0-9]{32,}", "[REDACTED_API_KEY]"),
            (r"AIza[a-zA-Z0-9\-_]{35}", "[REDACTED_GEMINI_KEY]"),
            
            # 2. Local User Paths (Atomic Detail)
            (re.escape(f"/Users/{self.username}"), "[USER_HOME]"),
            (re.escape(f"C:\\Users\\{self.username}"), "[USER_HOME]"),
            
            # 3. Communications
            (r"[\w\.-]+@[\w\.-]+\.\w+", "[REDACTED_EMAIL]"),
            (r"\+?\d{10,15}", "[REDACTED_PHONE]")
        ]

    def redact(self, text: str) -> str:
        if not text: return ""
        scrubbed = text
        for pattern, replacement in self.patterns:
            scrubbed = re.sub(pattern, replacement, scrubbed)
        return scrubbed

# Global instance
redactor = DeepRedactor()
