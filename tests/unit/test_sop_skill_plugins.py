from __future__ import annotations

from quentin.skills.manager import SkillManager


def test_sop_skill_plugin_discovery_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_SKILL_MD_ENABLED", "true")
    d = tmp_path / "extensions" / "skills" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: demo",
                "name: demo_skill",
                "description: Demo SOP skill",
                "---",
                "",
                "# Demo",
                "Do X then Y.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    mgr = SkillManager(repo_root=tmp_path)
    names = mgr.list_sop_prompts()
    assert "demo" in names

    text = mgr.load_sop_prompt("demo")
    assert "Demo SOP skill" in text or "Do X then Y" in text


def test_sop_skill_plugin_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QUENTIN_SKILL_MD_ENABLED", raising=False)
    monkeypatch.delenv("QUENTIN_SOP_SKILLS_ENABLED", raising=False)
    d = tmp_path / "extensions" / "skills" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: demo",
                "name: demo_skill",
                "description: Demo SOP skill",
                "---",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    mgr = SkillManager(repo_root=tmp_path)
    names = mgr.list_sop_prompts()
    assert "demo" not in names
