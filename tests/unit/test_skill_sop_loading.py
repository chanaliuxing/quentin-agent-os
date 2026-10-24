from __future__ import annotations

from pathlib import Path

from quentin.skills.manager import SkillManager


def test_sop_loaded_by_task_type() -> None:
    manager = SkillManager(repo_root=Path("."))
    names = manager.list_sop_prompts()
    assert "write_patch" in names
    assert "review_patch" in names

    sop = manager.load_sop_prompt("write_patch")
    assert "Goal:" in sop
    assert "Guardrails:" in sop

    chosen = manager.suggest_sop_for_task(task_text="please fix this patch failure", domain="core")
    assert chosen == "write_patch"


def test_missing_sop_fallback_to_default_prompt() -> None:
    manager = SkillManager(repo_root=Path("."))
    missing = manager.load_sop_prompt("nonexistent_sop")
    assert missing == ""

