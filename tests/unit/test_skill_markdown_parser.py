from __future__ import annotations

from quentin.skills.skill_markdown import load_skill_markdown_file, parse_skill_markdown


def test_parse_skill_markdown_extracts_frontmatter_fields() -> None:
    doc = parse_skill_markdown(
        "\n".join(
            [
                "---",
                "name: patch_skill",
                "description: Apply safe patch workflow",
                "triggers: [patch, fix]",
                "requires: [git, pytest]",
                "---",
                "",
                "# SOP",
                "Run tests first.",
            ]
        )
        + "\n"
    )
    assert doc.meta.name == "patch_skill"
    assert "patch" in doc.meta.triggers
    assert "git" in doc.meta.requires
    assert "Run tests first." in doc.body


def test_load_skill_markdown_file_defaults_id_from_folder(tmp_path) -> None:
    d = tmp_path / "extensions" / "skills" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(
        "\n".join(
            [
                "---",
                "name: demo_skill",
                "description: demo desc",
                "---",
                "",
                "demo body",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_skill_markdown_file(md)
    assert loaded.skill_id == "demo"
    assert loaded.name == "demo_skill"
    assert "demo body" in loaded.body
