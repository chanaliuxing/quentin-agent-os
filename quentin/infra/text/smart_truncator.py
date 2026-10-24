from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class SmartTruncator:
    """
    P5: Ported from OpenClaw's smart context pruning.
    Collapses large tool outputs while preserving semantic structure.
    """
    
    @staticmethod
    def truncate(content: str, max_chars: int = 4000, head_ratio: float = 0.7) -> str:
        """
        Main entry point for intelligent truncation.
        """
        if not content or len(content) <= max_chars:
            return content

        # 1. Try JSON Array Truncation
        stripped = content.strip()
        looks_like_json_array = stripped.startswith("[") and stripped.endswith("]")
        looks_like_wrapped_results = stripped.startswith('{"results":') and stripped.endswith("}")
        if looks_like_json_array or looks_like_wrapped_results:
            try:
                return SmartTruncator._truncate_json(content, max_chars)
            except Exception:
                pass

        # 2. Fallback to Head-Tail Truncation
        return SmartTruncator._head_tail(content, max_chars, head_ratio)

    @staticmethod
    def _truncate_json(content: str, max_chars: int) -> str:
        """
        Collapses middle items in a JSON array.
        """
        try:
            data = json.loads(content)
            items = []
            prefix = ""
            suffix = ""
            
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
                items = data["results"]
                prefix = '{"results": '
                suffix = '}'
            else:
                return SmartTruncator._head_tail(content, max_chars)

            if len(items) < 10:
                return SmartTruncator._head_tail(content, max_chars)

            # Keep first 3 and last 2
            head = items[:3]
            tail = items[-2:]
            collapsed_count = len(items) - 5
            
            # Extract keys for the summary message
            keys = set()
            if head and isinstance(head[0], dict):
                keys = set(head[0].keys())
            
            middle_msg = {
                "_type": "omitted_items",
                "count": collapsed_count,
                "note": f"Collapsed {collapsed_count} items to save context.",
                "item_schema_keys": list(keys)
            }
            
            truncated_list = head + [middle_msg] + tail
            return prefix + json.dumps(truncated_list, indent=2) + suffix
            
        except Exception:
            return SmartTruncator._head_tail(content, max_chars)

    @staticmethod
    def _head_tail(content: str, max_chars: int, head_ratio: float = 0.7) -> str:
        """
        Preserves the beginning and end of the text.
        """
        if len(content) <= max_chars:
            return content
            
        head_len = int(max_chars * head_ratio)
        tail_len = max_chars - head_len - 100  # Leave room for the message
        
        head = content[:head_len]
        tail = content[-tail_len:]
        
        return (
            f"{head}\n\n"
            f"--- [TRUNCATED: {len(content) - max_chars} characters collapsed for efficiency] ---\n\n"
            f"{tail}"
        )
