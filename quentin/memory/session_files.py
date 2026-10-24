from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class SessionFileEntry:
    path: str
    abs_path: str
    mtime_ms: float
    size: int
    hash: str
    content: str


@dataclass
class SessionFileDelta:
    path: str
    abs_path: str
    mtime_ms: float
    size: int
    hash: str
    content: str
    start_offset: int
    next_offset: int
    read_bytes: int
    message_count: int


def list_session_files_for_agent(agent_id: str, *, transcripts_root: str | Path = "data/sessions/transcripts") -> List[str]:
    root = Path(transcripts_root).resolve()
    base = root / str(agent_id or "").strip()
    if not base.exists() or not base.is_dir():
        return []
    return sorted(str(p.resolve()) for p in base.glob("*.jsonl") if p.is_file())


def session_path_for_file(abs_path: str | Path) -> str:
    return str(Path("sessions") / Path(abs_path).name).replace("\\", "/")


def _normalize_session_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split()).strip()


def extract_session_text(content: Any) -> Optional[str]:
    if isinstance(content, str):
        normalized = _normalize_session_text(content)
        return normalized or None
    if not isinstance(content, list):
        return None

    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        normalized = _normalize_session_text(text)
        if normalized:
            parts.append(normalized)
    if not parts:
        return None
    return " ".join(parts)


def _message_lines_from_jsonl_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    for line in lines:
        raw = (line or "").strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except Exception:
            continue
        if not isinstance(record, dict) or record.get("type") != "message":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = extract_session_text(message.get("content"))
        if not text:
            continue
        out.append(("User" if role == "user" else "Assistant") + f": {text}")
    return out


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_session_entry(abs_path: str | Path) -> Optional[SessionFileEntry]:
    p = Path(abs_path).resolve()
    if not p.exists() or not p.is_file():
        return None
    try:
        stat = p.stat()
        raw = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    lines = _message_lines_from_jsonl_lines(raw.splitlines())
    content = "\n".join(lines)
    return SessionFileEntry(
        path=session_path_for_file(p),
        abs_path=str(p),
        mtime_ms=float(stat.st_mtime * 1000.0),
        size=int(stat.st_size),
        hash=_hash_text(content),
        content=content,
    )


def build_session_delta(abs_path: str | Path, *, last_offset: int = 0) -> Optional[SessionFileDelta]:
    p = Path(abs_path).resolve()
    if not p.exists() or not p.is_file():
        return None
    try:
        stat = p.stat()
        size = int(stat.st_size)
    except Exception:
        return None

    start_offset = int(max(0, last_offset))
    if size < start_offset:
        start_offset = 0
    if size == start_offset:
        return None

    try:
        with p.open("rb") as f:
            f.seek(start_offset)
            raw_delta = f.read()
    except Exception:
        return None

    if not raw_delta:
        return None

    # Only consume complete JSONL lines so parser never sees partial trailing records.
    last_newline = raw_delta.rfind(b"\n")
    if last_newline < 0:
        return None
    consumed = raw_delta[: last_newline + 1]
    if not consumed:
        return None

    decoded = consumed.decode("utf-8", errors="ignore")
    message_lines = _message_lines_from_jsonl_lines(decoded.splitlines())
    content = "\n".join(message_lines)
    next_offset = start_offset + len(consumed)
    return SessionFileDelta(
        path=session_path_for_file(p),
        abs_path=str(p),
        mtime_ms=float(stat.st_mtime * 1000.0),
        size=size,
        hash=_hash_text(content),
        content=content,
        start_offset=start_offset,
        next_offset=next_offset,
        read_bytes=len(consumed),
        message_count=len(message_lines),
    )
