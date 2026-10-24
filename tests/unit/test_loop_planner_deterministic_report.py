from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from quentin.cognitive.loop_planner import _maybe_build_deterministic_report_plan, run_planner


def test_maybe_build_deterministic_report_plan_creates_exact_report_steps(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("repo guide\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    task = (
        "Inspect AGENTS.md and pyproject.toml, then create generated/brain_real_run_report.txt "
        "with exactly three lines: RUN_OK, AGENTS_PRESENT=yes or no, PYPROJECT_PRESENT=yes or no."
    )

    plan = _maybe_build_deterministic_report_plan(repo_root=tmp_path, task_text=task)

    assert isinstance(plan, dict)
    steps = plan["steps"]
    assert steps[0]["description"] == "Read the target file `AGENTS.md` using fs.read_file."
    assert steps[1]["description"] == "Read the target file `pyproject.toml` using fs.read_file."
    assert "generated/brain_real_run_report.txt" in steps[2]["description"]
    assert "AGENTS_PRESENT=yes" in steps[2]["description"]
    assert "PYPROJECT_PRESENT=yes" in steps[2]["description"]
    assert "yes or no" not in steps[2]["description"].lower()


def test_maybe_build_deterministic_report_plan_handles_trailing_punctuation(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("repo guide\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    task = (
        "Inspect AGENTS.md and pyproject.toml, then create generated/brain_real_run_report.txt "
        "with exactly three lines: RUN_OK, AGENTS_PRESENT=yes or no, PYPROJECT_PRESENT=yes or no."
    )

    plan = _maybe_build_deterministic_report_plan(repo_root=tmp_path, task_text=task)

    assert isinstance(plan, dict)
    step_desc = plan["steps"][2]["description"]
    assert '"RUN_OK\\nAGENTS_PRESENT=yes\\nPYPROJECT_PRESENT=yes"' in step_desc


def test_run_planner_uses_deterministic_report_plan_before_council(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("repo guide\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    called = {"council": 0}

    class _Loop:
        repo_root = tmp_path
        skill_manager = None
        knowledge_graph = None

        class council_manager:
            @staticmethod
            def run_council(name, question):  # type: ignore[no-untyped-def]
                _ = (name, question)
                called["council"] += 1
                raise AssertionError("planner council should not be called for deterministic report task")

    goal = SimpleNamespace(
        goal_id="g1",
        domain="core",
        description=(
            "Inspect AGENTS.md and pyproject.toml, then create generated/brain_real_run_report.txt "
            "with exactly three lines: RUN_OK, AGENTS_PRESENT=yes or no, PYPROJECT_PRESENT=yes or no."
        ),
        title="",
        metadata={},
    )

    payload = run_planner(_Loop(), goal, {})

    assert payload["goal_id"] == "g1"
    assert len(payload["steps"]) == 3
    assert called["council"] == 0
    raw = json.loads(payload["raw_output"])
    assert raw["source"] == "deterministic_report_plan"
