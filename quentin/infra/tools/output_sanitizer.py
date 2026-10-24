from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

TOOL_RESULT_MAX_CHARS = 8000
TOOL_ERROR_MAX_CHARS = 400

def truncate_tool_text(text: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(truncated)..."

def sanitize_tool_output(output: Any) -> Any:
    """
    P5: Ported from OpenClaw's sanitizeToolResult.
    Deep-prune massive fields that might overwhelm context.
    """
    if output is None:
        return None
    
    if isinstance(output, str):
        return truncate_tool_text(output)
        
    if isinstance(output, list):
        return [sanitize_tool_output(i) for i in output]
        
    if isinstance(output, dict):
        # Handle OpenClaw-style content blocks if present
        if "content" in output and isinstance(output["content"], list):
            sanitized_content = []
            for item in output["content"]:
                if isinstance(item, dict):
                    t = item.get("type")
                    if t == "text" and "text" in item:
                        item = {**item, "text": truncate_tool_text(item["text"])}
                    elif t == "image":
                        # Prune image data
                        item = {**item, "bytes": len(str(item.get("data", ""))), "omitted": True}
                        item.pop("data", None)
                sanitized_content.append(item)
            output = {**output, "content": sanitized_content}
            
        # Generic pruning for any large string field
        return {k: sanitize_tool_output(v) for k, v in output.items()}
        
    return output
