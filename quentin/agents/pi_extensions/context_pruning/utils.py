from __future__ import annotations

import hashlib
import re
from typing import Any, Dict


def normalize_repetition_text(text: str) -> str:
    s = str(text or "")
    s = re.sub(r"\d{2}:\d{2}:\d{2}", "", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    return s.strip().lower()


def stable_text_fingerprint(text: str) -> str:
    norm = normalize_repetition_text(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def msg_content(msg: Dict[str, Any]) -> str:
    return str((msg or {}).get("content") or "")

