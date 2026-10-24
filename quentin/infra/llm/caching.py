from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class CacheStrategy:
    """
    Implements Context Caching logic for Anthropic and Gemini.
    Aligned with OpenClaw's caching-ttl.
    """
    
    @staticmethod
    def apply_anthropic_cache(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Adds cache_control headers to large message blocks for Anthropic.
        Logic: Usually cache the second-to-last turn or large system prompts.
        """
        if len(messages) < 4:
            return messages
            
        new_messages = []
        for i, msg in enumerate(messages):
            msg_copy = dict(msg)
            # Mark the largest block for caching (e.g., middle of a long conversation)
            if i == len(messages) - 3:
                # Add metadata for Anthropic SDK
                msg_copy["cache_control"] = {"type": "ephemeral"}
            new_messages.append(msg_copy)
        return new_messages

    @staticmethod
    def should_use_cache(prompt_len: int) -> bool:
        """
        Caching is only economical for large contexts (e.g. > 32k tokens).
        """
        return prompt_len > 32000

# Global helper
