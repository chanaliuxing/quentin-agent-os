from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CompactionResult:
    compacted: bool
    summary: str
    text: str


def compact_text(text: str, max_chars: int) -> CompactionResult:
    if max_chars <= 0:
        return CompactionResult(compacted=False, summary="", text=text)
    if len(text) <= max_chars:
        return CompactionResult(compacted=False, summary="", text=text)
    summary_len = max(1, max_chars // 4)
    summary = text[:summary_len].strip()
    tail_len = max(1, max_chars - summary_len - 14)
    tail = text[-tail_len:].strip()
    compacted_text = f"{summary}\n\n[COMPRESSED]\n\n{tail}"
    return CompactionResult(compacted=True, summary=summary, text=compacted_text)


def trim_tool_result_text(text: str, *, keep_head: int = 1000, keep_tail: int = 1000) -> Tuple[str, bool]:
    """
    Deterministic tool-result trimming:
    keep head/tail and insert an explicit marker in the middle.
    """
    raw = str(text or "")
    n = len(raw)
    if n <= 0:
        return "", False
    if n <= keep_head + keep_tail + 64:
        return raw, False
    head = raw[: max(1, int(keep_head))]
    tail = raw[-max(1, int(keep_tail)) :]
    marker = f"[Tool result trimmed: kept first {keep_head} chars and last {keep_tail} chars of {n} chars.]"
    return f"{head}\n\n{marker}\n\n{tail}", True


def prune_history_texts(
    texts: List[str],
    max_chars: int,
    *,
    keep_recent: int = 0,
) -> Tuple[List[str], bool]:
    if max_chars <= 0:
        return texts, False
    if not texts:
        return texts, False

    keep_recent = max(0, int(keep_recent))
    recent = texts[-keep_recent:] if keep_recent > 0 else []
    older = texts[: max(0, len(texts) - len(recent))]

    kept_rev: List[str] = []
    total = 0
    for text in reversed(recent):
        total += len(text)
        if total > max_chars:
            break
        kept_rev.append(text)
    for text in reversed(older):
        total += len(text)
        if total > max_chars:
            break
        kept_rev.append(text)
    kept = list(reversed(kept_rev))
    return kept, len(kept) != len(texts)
