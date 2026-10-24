from __future__ import annotations

from quentin.utils.markdown_chunker import split_markdown_preserving_fences


def _chunk_fence_balance(chunk: str) -> bool:
    fences = 0
    for line in chunk.splitlines():
        if line.lstrip().startswith("```"):
            fences += 1
    return fences % 2 == 0


def test_markdown_chunker_preserves_fences() -> None:
    md = (
        "Hello\n"
        "```python\n"
        + ("print('x')\n" * 200)
        + "```\n"
        "Tail\n"
    )
    chunks = split_markdown_preserving_fences(md, max_chars=400)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 400 + 16  # allow small overhead for close+reopen fences
        assert _chunk_fence_balance(c.text)

