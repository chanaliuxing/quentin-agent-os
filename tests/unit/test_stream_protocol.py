from __future__ import annotations

from quentin.runtime.stream_protocol import StreamChunker, extract_reply_directives


def test_stream_chunker_separates_hidden_and_visible() -> None:
    text = "<think>internal plan</think> <final>Hello user</final>"
    out = StreamChunker(max_chunk_chars=10).process(text)
    assert out.hidden_thinking == "internal plan"
    assert out.visible_text == "Hello user"
    assert out.chunks


def test_stream_chunker_handles_thinking_alias_and_fallback() -> None:
    text = "<thinking>reasoning</thinking> visible text"
    out = StreamChunker().process(text)
    assert out.hidden_thinking == "reasoning"
    assert out.visible_text == "visible text"


def test_reply_directives_parse_and_strip() -> None:
    text = "[[media:https://a/b.png]] [[reply:abc-1]] [[silent]] hello"
    directives, cleaned = extract_reply_directives(text)
    assert directives.silent is True
    assert directives.reply_id == "abc-1"
    assert directives.media == ["https://a/b.png"]
    assert "[[" not in cleaned
