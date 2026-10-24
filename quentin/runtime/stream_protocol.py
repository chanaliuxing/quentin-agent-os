from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, List, Tuple


_DIRECTIVE_RE = re.compile(r"\[\[\s*([a-zA-Z0-9_.:-]+)\s*(?::\s*([^\]]+?)\s*)?\]\]")
_TAG_RE = re.compile(r"<(think|thinking|final)\b[^>]*>([\s\S]*?)</\1>", re.IGNORECASE)
_KNOWN_DIRECTIVE_KEYS = {"silent", "silent_reply", "reply.silent", "reply", "reply.id", "reply:id", "media", "media.url", "media:link", "media:id"}


@dataclass
class ReplyDirectives:
    raw: Dict[str, str] = field(default_factory=dict)
    media: List[str] = field(default_factory=list)
    reply_id: str = ""
    silent: bool = False


@dataclass
class StreamOutput:
    visible_text: str
    hidden_thinking: str
    directives: ReplyDirectives
    chunks: List[str]


def extract_reply_directives(text: str) -> Tuple[ReplyDirectives, str]:
    src = str(text or "")
    directives = ReplyDirectives()

    def _sub(m: re.Match[str]) -> str:
        key = str(m.group(1) or "").strip().lower()
        val = str(m.group(2) or "on").strip()
        if ":" in key:
            head, tail = key.split(":", 1)
            if head.strip() in _KNOWN_DIRECTIVE_KEYS:
                key = head.strip()
                if val == "on" and tail.strip():
                    val = tail.strip()
                elif val != "on" and tail.strip() and key in {"media"}:
                    val = f"{tail.strip()}:{val}"
        directives.raw[key] = val

        if key in {"silent", "silent_reply", "reply.silent"}:
            directives.silent = True
        elif key in {"reply", "reply.id", "reply:id"}:
            directives.reply_id = val
        elif key in {"media", "media.url", "media:link", "media:id"}:
            if val:
                directives.media.append(val)
        return ""

    cleaned = _DIRECTIVE_RE.sub(_sub, src)
    return directives, cleaned


def _extract_tagged_blocks(text: str) -> Tuple[str, str]:
    raw = str(text or "")
    hidden_parts: List[str] = []
    final_blocks: List[str] = []

    for m in _TAG_RE.finditer(raw):
        tag = str(m.group(1) or "").strip().lower()
        body = str(m.group(2) or "")
        if tag in {"think", "thinking"}:
            if body.strip():
                hidden_parts.append(body.strip())
        elif tag == "final":
            if body.strip():
                final_blocks.append(body.strip())

    if final_blocks:
        visible = final_blocks[-1]
    else:
        visible = re.sub(r"<think(?:ing)?\b[^>]*>[\s\S]*?</think(?:ing)?>", " ", raw, flags=re.IGNORECASE)
        visible = re.sub(r"</?final\b[^>]*>", " ", visible, flags=re.IGNORECASE)

    visible = re.sub(r"\s+", " ", visible).strip()
    hidden = "\n".join(hidden_parts).strip()
    return visible, hidden


def chunk_text(text: str, *, max_chars: int = 200) -> List[str]:
    src = str(text or "")
    if not src:
        return []
    cap = max(32, int(max_chars or 200))
    out: List[str] = []
    pos = 0
    while pos < len(src):
        end = min(len(src), pos + cap)
        if end < len(src):
            sp = src.rfind(" ", pos, end)
            if sp > pos + max(8, cap // 5):
                end = sp
        out.append(src[pos:end])
        pos = end
        while pos < len(src) and src[pos] == " ":
            pos += 1
    return out


class StreamChunker:
    def __init__(self, *, max_chunk_chars: int = 200):
        self.max_chunk_chars = max(32, int(max_chunk_chars or 200))

    def process(self, raw_text: str) -> StreamOutput:
        directives, no_directive = extract_reply_directives(str(raw_text or ""))
        visible, hidden = _extract_tagged_blocks(no_directive)
        visible = re.sub(r"\s+", " ", visible).strip()
        chunks = chunk_text(visible, max_chars=self.max_chunk_chars)
        return StreamOutput(
            visible_text=visible,
            hidden_thinking=hidden,
            directives=directives,
            chunks=chunks,
        )
