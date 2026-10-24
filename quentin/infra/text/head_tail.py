import logging

logger = logging.getLogger(__name__)

def truncate_head_tail(text: str, max_chars: int = 12000, head_ratio: float = 0.7, tail_ratio: float = 0.2) -> str:
    """
    Truncates text by keeping the first X% and last Y%, inserting a marker in between.
    Default: Keep 70% Head, 20% Tail, discard 10% middle.
    """
    if not text or len(text) <= max_chars:
        return text

    head_limit = int(max_chars * head_ratio)
    tail_limit = int(max_chars * tail_ratio)
    
    # Ensure we don't overlap if ratios are weird (though here 0.7 + 0.2 = 0.9)
    if head_limit + tail_limit >= len(text):
        return text

    head = text[:head_limit]
    tail = text[-tail_limit:]
    
    marker = f"\n\n[... TRUNCATED {len(text) - head_limit - tail_limit} CHARACTERS ...]\n\n"
    
    return head + marker + tail

def truncate_lines(text: str, max_lines: int = 200, head_lines_ratio: float = 0.7) -> str:
    """
    Line-based truncation version.
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    
    head_count = int(max_lines * head_lines_ratio)
    tail_count = max_lines - head_count
    
    head = lines[:head_count]
    tail = lines[-tail_count:]
    
    marker = f"[... TRUNCATED {len(lines) - max_lines} LINES ...]"
    
    result_lines = head + [marker] + tail
    return "\n".join(result_lines)
