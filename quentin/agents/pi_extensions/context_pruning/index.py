from __future__ import annotations

from typing import Any, Dict, List

from .repetition import is_redundant_error_message
from .size import squash_large_content
from .utils import msg_content


def prune_message_history(
    messages: List[Dict[str, Any]],
    *,
    seen_counts: Dict[str, int],
    repetition_threshold: int = 3,
) -> List[Dict[str, Any]]:
    if not messages:
        return []
    protected_indices = {0, len(messages) - 1, len(messages) - 2}
    out: List[Dict[str, Any]] = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if i in protected_indices:
            out.append(msg)
            continue
        content = msg_content(msg)
        if is_redundant_error_message(
            content=content,
            seen_counts=seen_counts,
            repetition_threshold=repetition_threshold,
        ):
            continue
        new_msg = dict(msg)
        new_msg["content"] = squash_large_content(content)
        out.append(new_msg)
    return out

