import json
from pathlib import Path

import pytest

from app.config import settings
from app.evidence import EventStore
from app.temporal.activities import generate_phase_tasks_activity


@pytest.mark.asyncio
async def test_generate_phase_tasks_activity_writes_typed_contract_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    result = await generate_phase_tasks_activity(
        project_id="p1",
        phase_id="phase_01",
        prd_content="# PRD\n\nTest module",
        module_name="module_main",
    )

    contract_files = result["contract_files"]
    task_spec_path = Path(contract_files["task_spec"])
    change_spec_path = Path(contract_files["change_spec"])
    acceptance_spec_path = Path(contract_files["acceptance_spec"])

    assert task_spec_path.exists()
    assert change_spec_path.exists()
    assert acceptance_spec_path.exists()

    task_spec = json.loads(task_spec_path.read_text(encoding="utf-8"))
    change_spec = json.loads(change_spec_path.read_text(encoding="utf-8"))
    acceptance_spec = json.loads(acceptance_spec_path.read_text(encoding="utf-8"))

    assert task_spec["task_id"] == "task_phase_01_module_main"
    assert "repo_root" in task_spec
    assert "worktree_path" in task_spec
    assert "base_sha" in task_spec
    assert "head_sha" in task_spec
    assert change_spec["task_id"] == task_spec["task_id"]
    assert acceptance_spec["task_id"] == task_spec["task_id"]

    dev_task_file = Path(result["dev_task"])
    dev_task_text = dev_task_file.read_text(encoding="utf-8")
    assert "Typed Contracts" in dev_task_text
    assert "task_spec.schema.json" in dev_task_text
    events = EventStore().read("p1", "phase_01")
    assert any(item.get("event_type") == "ARTIFACT_DECLARED" for item in events)


@pytest.mark.asyncio
async def test_generate_phase_tasks_applies_latest_human_review_patch(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()

    resolution_file = settings.hooks_dir / "phase_01_human_review_resolution.json"
    resolution_file.parent.mkdir(parents=True, exist_ok=True)
    resolution_file.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "decision": "approved",
                "reviewer": "lead",
                "notes": "Must bind required_tests to concrete gate plan.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await generate_phase_tasks_activity(
        project_id="p1",
        phase_id="phase_01",
        prd_content="# PRD\n\nTest module",
        module_name="module_main",
    )

    assert result["review_patch_applied"] is True
    planner_task_text = Path(result["planner_task"]).read_text(encoding="utf-8")
    assert "Human Review Patch" in planner_task_text
    assert "Must bind required_tests" in planner_task_text
    assert "Enforced Repair Constraints (Machine-Readable)" in planner_task_text


@pytest.mark.asyncio
async def test_generate_phase_tasks_emits_contract_lint_failed_event(monkeypatch, tmp_path):
    from app.temporal import activities

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()
    monkeypatch.setattr(activities, "lint_contract_coherence", lambda **kwargs: ["must_update_tests conflict"])

    with pytest.raises(ValueError):
        await generate_phase_tasks_activity(
            project_id="p1",
            phase_id="phase_01",
            prd_content="# PRD\n\nTest module",
            module_name="module_main",
        )

    events = EventStore().read("p1", "phase_01")
    assert any(
        item.get("event_type") == "CONTRACT_LINT_FAILED"
        and item.get("failure_type") == "INVALID_TASK_CONTRACT"
        for item in events
    )
