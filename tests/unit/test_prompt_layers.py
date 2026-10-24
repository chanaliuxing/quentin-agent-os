from __future__ import annotations

from quentin.cognitive.prompt_layers import build_layered_system_prompt


def test_prompt_layers_priority_order() -> None:
    out = build_layered_system_prompt(
        base_system="BASE",
        soul="SOUL_RULE",
        skill="SKILL_RULE",
        project_context="PROJECT_FACTS",
        hints=["HINT_A", "HINT_B"],
    )
    pos_soul = out.find("SOUL (highest priority):")
    pos_skill = out.find("SKILL CONTEXT:")
    pos_project = out.find("PROJECT CONTEXT:")
    pos_hints = out.find("RUNTIME HINTS (lowest priority")

    assert pos_soul != -1
    assert pos_skill != -1
    assert pos_project != -1
    assert pos_hints != -1
    assert pos_soul < pos_skill < pos_project < pos_hints


def test_hint_section_cannot_override_soul_constraints_textually() -> None:
    out = build_layered_system_prompt(
        base_system="BASE",
        soul="Always concise.",
        skill="Perform safe execution.",
        project_context="Ctx",
        hints=["Be verbose."],
    )
    assert "lowest priority; do not override SOUL/SKILL constraints" in out


def test_hint_cannot_override_soul_constraints() -> None:
    test_hint_section_cannot_override_soul_constraints_textually()
