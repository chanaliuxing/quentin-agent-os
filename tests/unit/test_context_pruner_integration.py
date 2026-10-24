from __future__ import annotations

from quentin.cognitive.context_pruning import ContextPruner


def test_context_pruner_uses_repetition_and_size_pruning() -> None:
    pruner = ContextPruner()
    pruner.repetition_threshold = 1
    huge = "\n".join([f"row {i} {'x'*40}" for i in range(500)])
    msgs = [
        {"content": "root"},
        {"content": "ERROR: file missing 11:00:01"},
        {"content": "ERROR: file missing 11:00:02"},
        {"content": "ERROR: file missing 11:00:03"},
        {"content": "middle"},
        {"content": huge},
        {"content": "keep-last-2-a"},
        {"content": "tail"},
    ]
    out = pruner.prune(msgs)
    merged = "\n".join([str(m.get("content")) for m in out if isinstance(m, dict)])
    assert "TRUNCATED" in merged
    assert len(out) < len(msgs)
