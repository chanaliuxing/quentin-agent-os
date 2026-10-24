from __future__ import annotations

from quentin.skills.manager import SkillManager


def test_skill_manager_markdown_list_is_metadata_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_SKILL_MD_ENABLED", "true")
    d = tmp_path / "extensions" / "skills" / "audit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: audit_skill",
                "name: audit_skill",
                "description: Audit security-related changes",
                "triggers: [audit, security, risk]",
                "---",
                "",
                "# Body",
                "Very long SOP content should not be loaded by list.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manager = SkillManager(repo_root=tmp_path)
    items = manager.list_markdown_skills()
    assert len(items) == 1
    assert items[0]["skill_id"] == "audit_skill"
    assert "body" not in items[0]

    loaded = manager.load_markdown_skill("audit_skill")
    assert "Very long SOP content" in loaded.get("body", "")


def test_skill_manager_markdown_trigger_match_and_sop_pick(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_SKILL_MD_ENABLED", "true")
    d = tmp_path / "extensions" / "skills" / "fixer"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: fix_skill",
                "name: fix_skill",
                "description: Repair build and patch issues",
                "triggers: [fix, patch, build failure]",
                "---",
                "",
                "# Fix SOP",
                "Run tests then patch.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manager = SkillManager(repo_root=tmp_path)
    matched = manager.match_markdown_skills("please fix patch build failure", top_k=1)
    assert matched
    assert matched[0]["skill_id"] == "fix_skill"

    selected = manager.suggest_sop_for_task("please fix patch build failure")
    assert selected == "fix_skill"
