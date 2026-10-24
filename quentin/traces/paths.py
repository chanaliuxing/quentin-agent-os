from __future__ import annotations

import os
from pathlib import Path


def resolve_traces_dir(*, repo_root: str | Path = ".") -> Path:
    """
    Resolve traces directory, honoring QUENTIN_TRACES_DIR override.

    This keeps trace writers and trace consumers consistent and makes the
    storage pluggable via environment/config without hardcoding `data/traces/`.
    """
    root = Path(repo_root).resolve()
    override = (os.getenv("QUENTIN_TRACES_DIR") or "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (root / p).resolve()
        return p
    return (root / "data" / "traces").resolve()


def resolve_events_path(*, repo_root: str | Path = ".") -> Path:
    return resolve_traces_dir(repo_root=repo_root) / "events.jsonl"


def resolve_summaries_path(*, repo_root: str | Path = ".") -> Path:
    return resolve_traces_dir(repo_root=repo_root) / "summaries.jsonl"


def resolve_lessons_path(*, repo_root: str | Path = ".") -> Path:
    return resolve_traces_dir(repo_root=repo_root) / "lessons.jsonl"

