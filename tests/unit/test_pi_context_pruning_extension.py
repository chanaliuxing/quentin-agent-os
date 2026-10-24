from __future__ import annotations

from quentin.agents.pi_extensions.context_pruning import prune_message_history


def test_prune_message_history_drops_redundant_error_messages() -> None:
    seen = {}
    msgs = [
        {"content": "root"},
        {"content": "ERROR: permission denied at 12:00:00"},
        {"content": "ERROR: permission denied at 12:00:01"},
        {"content": "ERROR: permission denied at 12:00:02"},
        {"content": "ERROR: permission denied at 12:00:03"},
        {"content": "keep-last-2-a"},
        {"content": "tail"},
    ]
    out = prune_message_history(msgs, seen_counts=seen, repetition_threshold=1)
    contents = [str(m.get("content")) for m in out if isinstance(m, dict)]
    assert any("tail" == c for c in contents)
    assert len(out) < len(msgs)


def test_prune_message_history_squashes_large_content() -> None:
    seen = {}
    big = "\n".join([f"line {i} {'x'*40}" for i in range(600)])
    msgs = [{"content": "root"}, {"content": big}, {"content": "keep-last-2-a"}, {"content": "tail"}]
    out = prune_message_history(msgs, seen_counts=seen, repetition_threshold=3)
    merged = "\n".join([str(m.get("content")) for m in out if isinstance(m, dict)])
    assert "TRUNCATED" in merged
