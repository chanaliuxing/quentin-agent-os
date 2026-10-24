from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MarkdownChunk:
    text: str
    is_truncated: bool = False


def split_markdown_preserving_fences(markdown: str, *, max_chars: int) -> List[MarkdownChunk]:
    """
    Split markdown into chunks <= max_chars while preserving fenced code blocks.

    Strategy (OpenClaw-style):
    - Never cut a chunk while a fence is open.
    - If splitting inside a fence is required, close the fence, split, then reopen it.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    text = markdown or ""
    if len(text) <= max_chars:
        return [MarkdownChunk(text=text, is_truncated=False)]

    lines = text.splitlines(keepends=True)
    chunks: List[MarkdownChunk] = []
    buf: List[str] = []
    buf_len = 0

    in_fence = False
    fence_open_line: Optional[str] = None

    def flush(*, truncated: bool) -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunks.append(MarkdownChunk(text="".join(buf), is_truncated=truncated))
        buf = []
        buf_len = 0

    def append_piece(piece: str) -> None:
        nonlocal buf_len
        buf.append(piece)
        buf_len += len(piece)

    for line in lines:
        stripped = line.lstrip()
        is_fence = stripped.startswith("```")

        # If the next line doesn't fit, flush the current chunk first.
        if buf and (buf_len + len(line) > max_chars):
            if in_fence and fence_open_line:
                append_piece("```\n")
                flush(truncated=True)
                append_piece(fence_open_line + "\n")
            else:
                flush(truncated=True)

        # Handle pathological long line.
        if len(line) > max_chars:
            # Emit current buffer first.
            if buf:
                if in_fence and fence_open_line:
                    append_piece("```\n")
                    flush(truncated=True)
                    append_piece(fence_open_line + "\n")
                else:
                    flush(truncated=True)

            # Split the long line.
            remaining = line
            while remaining:
                take = remaining[:max_chars]
                remaining = remaining[max_chars:]
                if in_fence and fence_open_line:
                    # Keep fence integrity per chunk.
                    chunk_text = fence_open_line + "\n" + take
                    if not chunk_text.endswith("\n"):
                        chunk_text += "\n"
                    chunk_text += "```\n"
                    chunks.append(MarkdownChunk(text=chunk_text, is_truncated=bool(remaining)))
                else:
                    chunks.append(MarkdownChunk(text=take, is_truncated=bool(remaining)))
            continue

        # Toggle fence state after budgeting decisions (so close+reopen keeps correctness).
        if is_fence:
            if in_fence:
                in_fence = False
                fence_open_line = None
            else:
                in_fence = True
                fence_open_line = stripped.rstrip("\n")

        append_piece(line)

    if in_fence:
        append_piece("```\n")
    flush(truncated=False)
    return chunks

