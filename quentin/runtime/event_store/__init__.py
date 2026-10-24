from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quentin.runtime.event_store.base import EventStoreBackend
from quentin.runtime.event_store.file_backend import FileEventStoreBackend
from quentin.runtime.event_store.noop_backend import NoopEventStoreBackend


def build_event_store_backend(*, repo_root: str | Path = ".") -> EventStoreBackend:
    """
    Factory for EventStoreBackend selection (Blueprint v3 P2-C).

    Canonical config:
    - QUENTIN_OBS_EVENT_STORE_BACKEND=file (default)
    - QUENTIN_OBS_EVENT_STORE_BACKEND=noop
    """
    kind = (os.getenv("QUENTIN_OBS_EVENT_STORE_BACKEND", "file") or "").strip().lower()
    root = Path(repo_root).resolve()

    if kind in ("", "file", "jsonl"):
        return FileEventStoreBackend(repo_root=root)
    if kind in ("noop", "null", "disabled", "off", "0", "false"):
        return NoopEventStoreBackend()

    # Fail-safe: unknown kind should not crash the brain; fall back to file.
    return FileEventStoreBackend(repo_root=root)


__all__ = [
    "build_event_store_backend",
    "EventStoreBackend",
    "FileEventStoreBackend",
    "NoopEventStoreBackend",
]

