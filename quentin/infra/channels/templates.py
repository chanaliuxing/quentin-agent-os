from __future__ import annotations

import logging
from typing import Dict, Any, Optional

class ResponseTemplate:
    """
    Formats AI replies with dynamic prefixes and metadata.
    Ported from OpenClaw's auto-reply/reply/response-prefix-template.
    """
    
    @staticmethod
    def format_reply(text: str, model_id: str, provider: str, usage: Dict[str, Any] = None, latency: float = 0.0) -> str:
        """
        1:1 Atomic Parity with OpenClaw Reply Format.
        Includes the standard footer: [Usage: I:XX O:YY | $0.00 | 0.0s]
        """
        icon_map = {
            "openai": "🤖", "anthropic": "🎭", "google": "♊", 
            "deepseek": "🐋", "ollama": "🦙"
        }
        icon = icon_map.get(provider.lower(), "🧠")
        
        # 1. Header
        header = f"[{icon} {model_id.upper()}]"
        
        # 2. Body
        body = text.strip()
        
        # 3. Footer (OpenClaw Atomic Parity)
        if usage:
            i_tokens = usage.get("prompt_tokens", 0)
            o_tokens = usage.get("completion_tokens", 0)
            cost = usage.get("cost_usd", 0.0)
            footer = f"\n\n[Usage: I:{i_tokens} O:{o_tokens} | ${cost:.4f} | {latency:.1f}s]"
        else:
            footer = f"\n\n[Latency: {latency:.1f}s]"
            
        return f"{header}\n\n{body}{footer}"

    @staticmethod
    def format_alert(title: str, body: str) -> str:
        return f"⚠️ **{title}**\n\n{body}"

# Global instance
reply_formatter = ResponseTemplate()