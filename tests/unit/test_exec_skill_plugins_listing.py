from __future__ import annotations

from quentin.skills.manager import SkillManager


def test_list_exec_skill_plugins(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "extensions" / "skills" / "demo_exec"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: demo_exec",
                "name: demo.exec",
                "description: demo",
                "domain: core",
                "tags: [x, y]",
                "entrypoint: logic:run",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (d / "logic.py").write_text("def run(step, goal, context):\n    return {'status':'ok'}\n", encoding="utf-8")

    mgr = SkillManager(repo_root=tmp_path)
    items = mgr.list_exec_skill_plugins(domain="core")
    assert any(it.get("skill_id") == "demo_exec" for it in items)
