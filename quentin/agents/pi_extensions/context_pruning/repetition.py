from __future__ import annotations

from typing import Dict

from .utils import stable_text_fingerprint


def is_redundant_error_message(
    *,
    content: str,
    seen_counts: Dict[str, int],
    repetition_threshold: int = 3,
) -> bool:
    text = str(content or "")
    if "error" not in text.lower():
        return False
    fp = stable_text_fingerprint(text)
    cnt = int(seen_counts.get(fp, 0))
    seen_counts[fp] = cnt + 1
    return cnt >= max(1, int(repetition_threshold))

