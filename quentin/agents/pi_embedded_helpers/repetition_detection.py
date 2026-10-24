from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RepetitionState:
    last_signature: str = ""
    consecutive_count: int = 0


def update_repetition_state(state: RepetitionState, signature: str) -> RepetitionState:
    sig = str(signature or "").strip()
    if not sig:
        return RepetitionState(last_signature="", consecutive_count=0)
    if sig == state.last_signature:
        return RepetitionState(last_signature=sig, consecutive_count=state.consecutive_count + 1)
    return RepetitionState(last_signature=sig, consecutive_count=1)


def detect_repetitive_sequence(signatures: List[str], *, window: int = 3) -> Optional[str]:
    vals = [str(s or "").strip() for s in signatures if str(s or "").strip()]
    if len(vals) < max(2, int(window)):
        return None
    tail = vals[-window:]
    if len(set(tail)) == 1:
        return tail[0]
    return None

