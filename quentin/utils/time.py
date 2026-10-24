from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Union


def now_utc() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)

def now_utc_iso() -> str:
    """Return timezone-aware UTC ISO timestamp."""
    return now_utc().isoformat()

def now_local_iso() -> str:
    """Return local timezone-aware ISO timestamp."""
    return datetime.now().astimezone().isoformat()

def now_iso() -> str:
    """
    Return current timestamp as ISO string.
    Canonical internal timestamp: UTC (`+00:00`).
    """
    return now_utc_iso()


def now_display_iso() -> str:
    """
    Display-oriented timestamp.
    Uses local timezone only when QUENTIN_LOG_LOCAL_TIME=1.
    """
    use_local = os.getenv("QUENTIN_LOG_LOCAL_TIME", "0").strip().lower() in ("1", "true", "yes", "on")
    if use_local:
        return now_local_iso()
    return now_utc_iso()


def normalize_to_utc_iso(value: Union[str, datetime]) -> str:
    """
    Normalize input timestamp into timezone-aware UTC ISO string.
    - Naive datetime/string is treated as UTC.
    - Aware datetime/string is converted to UTC.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()
