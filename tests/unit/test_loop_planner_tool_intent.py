from __future__ import annotations

from quentin.cognitive.loop_planner import _normalize_step_tool_intent


def test_normalize_step_tool_intent_infers_expected_tool_from_description() -> None:
    out = _normalize_step_tool_intent(
        {
            "description": "Use fs.read_file to inspect quentin/cognitive/loop_planner.py",
            "notes": "verify state first",
        }
    )
    assert out.get("expected_tool") == "fs.read_file"
    assert "filesystem" in list(out.get("allowed_fallback_families") or [])


def test_normalize_step_tool_intent_preserves_explicit_intent() -> None:
    out = _normalize_step_tool_intent(
        {
            "description": "Check status",
            "tool_intent": {
                "expected_tool": "shell.run_command",
                "allowed_fallback_families": ["shell"],
                "why": "verification",
            },
        }
    )
    assert out.get("expected_tool") == "shell.run_command"
    assert out.get("allowed_fallback_families") == ["shell"]
    assert out.get("why") == "verification"
