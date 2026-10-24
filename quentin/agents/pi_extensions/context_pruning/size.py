from __future__ import annotations


def squash_large_content(content: str, *, min_chars: int = 5000, max_lines: int = 100) -> str:
    text = str(content or "")
    if len(text) < max(1, int(min_chars)):
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head_n = 10
    tail_n = 10
    omitted = max(0, len(lines) - head_n - tail_n)
    head = "\n".join(lines[:head_n])
    tail = "\n".join(lines[-tail_n:])
    marker = f"\n\n... [TRUNCATED: {omitted} lines of repetitive data squashed for focus] ...\n\n"
    return head + marker + tail

