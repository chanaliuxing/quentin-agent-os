import pytest
import json

from app.models import AgentRole, AgentStatus, validate_output_contract
from app.temporal import activities
from app.temporal.workflow import _topological_levels
from app.config import settings
from app.utils import get_result_file


@pytest.mark.asyncio
async def test_run_module_pipeline_activity_uses_planner_reviewer(monkeypatch):
    calls: list[str] = []

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        calls.append(agent_name)
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {"verdict": "approved"},
            }
        return {"agent": agent_name, "status": AgentStatus.SUCCESS.value, "contract": {}}

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "success"
    assert calls == [
        AgentRole.PLANNER.value,
        AgentRole.REVIEWER.value,
        AgentRole.DEV.value,
        AgentRole.QA.value,
    ]


@pytest.mark.asyncio
async def test_run_module_pipeline_materializes_missing_planner_result_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        if agent_name == AgentRole.PLANNER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-09T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "plan_summary": "ok",
                    "tasks": ["t1"],
                    "acceptance_criteria": ["c1"],
                },
            }
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-09T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "verdict": "approved",
                    "findings": [],
                    "finding_codes": [],
                },
            }
        if agent_name == AgentRole.DEV.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-09T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "status": "success",
                    "files_changed": ["app/module_main/main.py"],
                    "implementation_notes": "ok",
                },
            }
        return {
            "agent": agent_name,
            "status": AgentStatus.SUCCESS.value,
            "contract": {
                "contract_version": "1.0",
                "generated_at": "2026-03-09T00:00:00Z",
                "constraints_ack": True,
                "module_name": module_name,
                "status": "pass",
                "tests_run": 1,
                "tests_passed": 1,
                "tests_failed": 0,
                "issues": [],
            },
        }

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "success"
    planner_file = get_result_file("phase_01", AgentRole.PLANNER, "module_main")
    assert planner_file.exists()
    planner_contract = validate_output_contract(AgentRole.PLANNER, planner_file.read_text(encoding="utf-8"))
    assert planner_contract.plan_summary == "ok"


def test_topological_levels_groups_parallel_modules():
    modules = [
        {"name": "module_a", "depends_on": []},
        {"name": "module_b", "depends_on": []},
        {"name": "module_c", "depends_on": ["module_a"]},
    ]
    levels = _topological_levels(modules)
    assert len(levels) == 2
    assert {m["name"] for m in levels[0]} == {"module_a", "module_b"}
    assert {m["name"] for m in levels[1]} == {"module_c"}


@pytest.mark.asyncio
async def test_run_module_pipeline_blocks_dev_when_reviewer_not_approved(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    calls: list[str] = []

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        calls.append(agent_name)
        if agent_name == AgentRole.PLANNER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-10T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "plan_summary": "ok",
                    "tasks": ["t1"],
                    "acceptance_criteria": ["c1"],
                },
            }
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {"verdict": "needs_revision", "findings": ["x"]},
            }
        return {"agent": agent_name, "status": AgentStatus.SUCCESS.value, "contract": {}}

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    monkeypatch.setattr(activities.settings, "max_planner_reviewer_loops", 2)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    assert AgentRole.DEV.value not in calls
    assert AgentRole.QA.value not in calls
    assert result["review_stagnated"] is True
    dev_file = get_result_file("phase_01", AgentRole.DEV, "module_main")
    qa_file = get_result_file("phase_01", AgentRole.QA, "module_main")
    assert dev_file.exists()
    assert qa_file.exists()
    assert validate_output_contract(AgentRole.DEV, dev_file.read_text(encoding="utf-8")).status == "failed"
    assert validate_output_contract(AgentRole.QA, qa_file.read_text(encoding="utf-8")).status == "fail"


@pytest.mark.asyncio
async def test_run_module_pipeline_clears_stale_result_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    stale_dev_file = get_result_file("phase_01", AgentRole.DEV, "module_main")
    stale_dev_file.parent.mkdir(parents=True, exist_ok=True)
    stale_dev_file.write_text('{"stale": true}', encoding="utf-8")

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {"verdict": "needs_revision", "findings": ["x"]},
            }
        return {"agent": agent_name, "status": AgentStatus.SUCCESS.value, "contract": {}}

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    monkeypatch.setattr(activities.settings, "max_planner_reviewer_loops", 0)
    await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert stale_dev_file.exists()


@pytest.mark.asyncio
async def test_run_module_pipeline_writes_reviewer_fallback_when_planner_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        if agent_name == AgentRole.PLANNER.value:
            return {"agent": agent_name, "status": AgentStatus.FAILED.value, "contract": {}}
        raise AssertionError("unexpected agent call")

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    reviewer_file = get_result_file("phase_01", AgentRole.REVIEWER, "module_main")
    assert reviewer_file.exists()
    reviewer_contract = validate_output_contract(AgentRole.REVIEWER, reviewer_file.read_text(encoding="utf-8"))
    assert reviewer_contract.verdict == "needs_revision"


@pytest.mark.asyncio
async def test_run_module_pipeline_blocks_when_planner_handoff_contract_not_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    calls: list[str] = []

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        calls.append(agent_name)
        if agent_name == AgentRole.PLANNER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {},  # invalid/empty planner payload should fail handoff verification
            }
        raise AssertionError("unexpected downstream agent call")

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    assert calls == [AgentRole.PLANNER.value]
    assert result["planner_result"]["failure_type"] == "PLANNER_HANDOFF_STATE_MISMATCH"
    assert result["state_contracts"]
    latest_contract = result["state_contracts"][-1]
    assert latest_contract["verified"] is False
    assert latest_contract["observed_state"]["contract_valid"] is False
    reviewer_file = get_result_file("phase_01", AgentRole.REVIEWER, "module_main")
    assert reviewer_file.exists()
    reviewer_contract = validate_output_contract(AgentRole.REVIEWER, reviewer_file.read_text(encoding="utf-8"))
    assert reviewer_contract.verdict == "needs_revision"


@pytest.mark.asyncio
async def test_run_module_pipeline_blocks_qa_when_dev_handoff_contract_not_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    calls: list[str] = []

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        calls.append(agent_name)
        if agent_name == AgentRole.PLANNER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-10T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "plan_summary": "ok",
                    "tasks": ["t1"],
                    "acceptance_criteria": ["c1"],
                },
            }
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-10T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "verdict": "approved",
                    "findings": [],
                    "finding_codes": [],
                },
            }
        if agent_name == AgentRole.DEV.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {},  # invalid dev payload triggers handoff mismatch
            }
        raise AssertionError("unexpected QA call")

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    assert AgentRole.QA.value not in calls
    assert result["dev_result"]["failure_type"] == "DEV_HANDOFF_STATE_MISMATCH"
    assert result["dev_result"]["status"] == AgentStatus.FAILED.value
    assert result["state_contracts"]
    dev_contracts = [item for item in result["state_contracts"] if ":dev_handoff:" in item["action_id"]]
    assert dev_contracts
    assert dev_contracts[-1]["verified"] is False


@pytest.mark.asyncio
async def test_run_module_pipeline_marks_failure_when_qa_handoff_contract_not_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    calls: list[str] = []

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        calls.append(agent_name)
        if agent_name == AgentRole.PLANNER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-23T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "plan_summary": "ok",
                    "tasks": ["t1"],
                    "acceptance_criteria": ["c1"],
                },
            }
        if agent_name == AgentRole.REVIEWER.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-23T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "verdict": "approved",
                    "findings": [],
                    "finding_codes": [],
                },
            }
        if agent_name == AgentRole.DEV.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {
                    "contract_version": "1.0",
                    "generated_at": "2026-03-23T00:00:00Z",
                    "constraints_ack": True,
                    "module_name": module_name,
                    "status": "success",
                    "files_changed": ["app/module_main/pipeline.py"],
                    "implementation_notes": "ok",
                },
            }
        if agent_name == AgentRole.QA.value:
            return {
                "agent": agent_name,
                "status": AgentStatus.SUCCESS.value,
                "contract": {},  # invalid QA payload triggers mismatch
            }
        raise AssertionError("unexpected agent call")

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    assert calls == [
        AgentRole.PLANNER.value,
        AgentRole.REVIEWER.value,
        AgentRole.DEV.value,
        AgentRole.QA.value,
    ]
    assert result["qa_result"]["failure_type"] == "QA_HANDOFF_STATE_MISMATCH"
    assert result["qa_result"]["status"] == AgentStatus.FAILED.value
    qa_contracts = [item for item in result["state_contracts"] if ":qa_handoff:" in item["action_id"]]
    assert qa_contracts
    assert qa_contracts[-1]["verified"] is False


@pytest.mark.asyncio
async def test_run_module_pipeline_restores_previous_planner_result_on_repair_round_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    planner_file = get_result_file("phase_01", AgentRole.PLANNER, "module_main")
    planner_file.parent.mkdir(parents=True, exist_ok=True)
    planner_file.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": "2026-03-09T00:00:00Z",
                "constraints_ack": True,
                "module_name": "module_main",
                "plan_summary": "previous-plan",
                "tasks": ["t1"],
                "acceptance_criteria": ["c1"],
            }
        ),
        encoding="utf-8",
    )

    async def fake_run_agent_activity(project_id: str, phase_id: str, agent_name: str, module_name: str | None):
        if agent_name == AgentRole.PLANNER.value:
            return {"agent": agent_name, "status": AgentStatus.FAILED.value, "contract": {}}
        raise AssertionError("unexpected agent call")

    monkeypatch.setattr(activities, "run_agent_activity", fake_run_agent_activity)
    result = await activities.run_module_pipeline_activity("p1", "phase_01", "module_main")
    assert result["status"] == "failed"
    assert planner_file.exists()
    planner_contract = validate_output_contract(AgentRole.PLANNER, planner_file.read_text(encoding="utf-8"))
    assert planner_contract.plan_summary == "previous-plan"


def test_write_failure_contract_result_does_not_overwrite_existing_primary(tmp_path):
    reviewer_file = tmp_path / "main_reviewer.md"
    reviewer_file.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": "2026-03-08T00:00:00Z",
                "constraints_ack": True,
                "module_name": "main",
                "verdict": "needs_revision",
                "findings": ["path conflict"],
                "finding_codes": ["PATH_CONFLICT"],
            }
        ),
        encoding="utf-8",
    )
    wrote = activities._write_failure_contract_result(
        result_file=reviewer_file,
        agent_role=AgentRole.REVIEWER,
        module_name="main",
        reason="blocked_by_planner",
        failure_type="RUNNER_BLOCKED",
    )
    assert wrote is False
    reviewer_contract = validate_output_contract(AgentRole.REVIEWER, reviewer_file.read_text(encoding="utf-8"))
    assert reviewer_contract.finding_codes[0] == "PATH_CONFLICT"
    metadata_file = reviewer_file.with_name("main_reviewer.meta.json")
    assert metadata_file.exists()
