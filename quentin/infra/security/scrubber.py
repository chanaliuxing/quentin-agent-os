from __future__ import annotations
import re
import logging
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)

class CredentialScrubber:
    """
    P5: Ported from OpenClaw's security sanitizers.
    Scrub sensitive patterns (API Keys, Tokens, Passwords) from text and structured data.
    """
    
    # Common sensitive patterns
    PATTERNS = {
        "OPENAI_KEY": r"sk-[a-zA-Z0-9]{32,}",
        "ANTHROPIC_KEY": r"sk-ant-[a-zA-Z0-9_-]{60,}",
        "GOOGLE_KEY": r"AIza[0-9A-Za-z-_]{35}",
        "GENERIC_SECRET": r"(?i)(password|passwd|secret|auth_token|access_token|private_key)[\'\"]?\s*[:=]\s*[\'\"]?([a-zA-Z0-9_\-\.\~]{8,})[\'\"]?",
        "GITHUB_TOKEN": r"gh[p_o_u_s_r]_[a-zA-Z0-9]{36,}",
        "JWT_TOKEN": r"ey[a-zA-Z0-9_=]+\.ey[a-zA-Z0-9_=]+\.[a-zA-Z0-9_\-\+\/=]+",
    }

    @classmethod
    def scrub_text(cls, text: str) -> str:
        """
        Applies all patterns to redaction.
        """
        if not text:
            return ""
            
        scrubbed = text
        for name, pattern in cls.PATTERNS.items():
            # For secrets with keys, we want to keep the key but hide the value
            if "GENERIC_SECRET" in name:
                scrubbed = re.sub(pattern, r"\1: [[REDACTED_SECRET]]", scrubbed)
            else:
                scrubbed = re.sub(pattern, f"[[REDACTED_{name}]]", scrubbed)
                
        return scrubbed

    @classmethod
    def scrub_data(cls, data: Any) -> Any:
        """
        Recursively scrubs strings within dicts or lists.
        """
        if isinstance(data, str):
            return cls.scrub_text(data)
        elif isinstance(data, dict):
            return {k: cls.scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.scrub_data(i) for i in data]
        return data
