from __future__ import annotations

import os
import logging
from typing import Dict, List, Set

class EnvScrubber:
    """
    Handles Environment Masking for Sub-agents.
    Aligned with OpenClaw's Sandbox/Agent isolation logic.
    """
    
    # Sensitive keys that should NEVER be passed to sub-agents as-is
    SENSITIVE_KEYS = {
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
        "AWS_SECRET_ACCESS_KEY", "PG_PASSWORD", "TELEGRAM_BOT_TOKEN"
    }

    @staticmethod
    def get_safe_env(allowed_keys: Set[str] = None) -> Dict[str, str]:
        """
        Returns a redacted environment dictionary.
        """
        raw_env = os.environ.copy()
        safe_env = {}
        
        for k, v in raw_env.items():
            if k in EnvScrubber.SENSITIVE_KEYS:
                safe_env[k] = "[MASKED_BY_GOVERNANCE]"
            elif allowed_keys and k not in allowed_keys:
                continue # Skip non-whitelisted keys
            else:
                safe_env[k] = v
                
        return safe_env

# Global helper
