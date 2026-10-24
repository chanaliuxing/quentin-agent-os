from __future__ import annotations

from quentin.memory.processors.gist_extractor import extract_gist_rules


def test_gist_extractor_emits_rules() -> None:
    rules = extract_gist_rules(
        [
            "tool_not_found: mcp.foo.bar",
            "permission denied while writing file",
            "Invalid JSON in model output",
        ],
        max_rules=8,
    )
    assert rules
    assert any("tool" in r.lower() for r in rules)

