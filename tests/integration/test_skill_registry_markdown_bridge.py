from __future__ import annotations

from pathlib import Path

from quentin.skills.manager import SkillManager


def test_markdown_skill_bridge_creates_registry_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_SKILL_MD_ENABLED", "true")
    skill_dir = tmp_path / "extensions" / "skills" / "bridge_demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: bridge_skill",
                "name: bridge_skill",
                "description: Bridge SOP to registry",
                "domain: core",
                "triggers: [bridge, registry]",
                "---",
                "",
                "# SOP",
                "Do bridge steps.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manager = SkillManager(repo_root=tmp_path)
    created = manager.bridge_registry_with_markdown()
    assert "bridge_skill" in created

    spec = manager.registry.get("bridge_skill")
    assert spec is not None
    assert spec.name == "bridge_skill"
    assert spec.domain == "core"
    assert "bridge" in (spec.tags or [])
