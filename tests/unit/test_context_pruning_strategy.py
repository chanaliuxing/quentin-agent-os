from __future__ import annotations

from quentin.llm.compaction import prune_history_texts, trim_tool_result_text


def test_keep_recent_turns() -> None:
    texts = [
        "turn1-" + ("a" * 20),
        "turn2-" + ("b" * 20),
        "turn3-" + ("c" * 20),
        "turn4-" + ("d" * 20),
    ]
    pruned, changed = prune_history_texts(texts, max_chars=80, keep_recent=2)
    assert changed is True
    # keep recent turns prioritized
    assert any(t.startswith("turn3-") for t in pruned)
    assert any(t.startswith("turn4-") for t in pruned)


def test_tool_result_trim_head_tail() -> None:
    src = "HEAD" + ("x" * 5000) + "TAIL"
    trimmed, changed = trim_tool_result_text(src, keep_head=16, keep_tail=16)
    assert changed is True
    assert trimmed.startswith(src[:16])
    assert trimmed.endswith(src[-16:])


def test_trim_marker_contains_original_size() -> None:
    src = "A" * 4096
    trimmed, changed = trim_tool_result_text(src, keep_head=32, keep_tail=32)
    assert changed is True
    assert "Tool result trimmed" in trimmed
    assert "4096" in trimmed

