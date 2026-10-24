from __future__ import annotations

from types import SimpleNamespace

from quentin.execution.skill_executor import Executor, StepExecutionRecord
from quentin.skills.manager import SkillManager


def test_executor_runs_exec_skill_plugin(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "extensions" / "skills" / "demo_exec"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.yaml").write_text(
        "\n".join(
            [
                "id: demo_exec",
                "name: demo.exec",
                "description: demo",
                "entrypoint: logic:run",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (d / "logic.py").write_text(
        "\n".join(
            [
                "def run(step, goal, context):",
                "    _ = (step, goal, context)",
                "    return {'status': 'ok', 'value': 42}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ex = Executor(repo_root=tmp_path, skill_manager=SkillManager(repo_root=tmp_path))
    rec = StepExecutionRecord(step_id="s1", description="x", skill_id="demo_exec", executor_mode="noop", success=False)
    ok = ex._try_execute_skill(step={"step_id": "s1", "description": "x"}, goal=SimpleNamespace(), context={}, record=rec)
    assert ok is True
    assert rec.success is True
    assert isinstance(rec.result, dict)
    assert rec.result.get("value") == 42
