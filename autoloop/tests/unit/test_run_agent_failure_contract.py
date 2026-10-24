import pytest
import json

from app.config import settings
from app.evidence import EventStore
from app.models import AgentRole, AgentStatus, validate_output_contract
from app.runners.base import AgentRunResult
from app.temporal import activities
from app.utils import ensure_phase_dirs, get_contract_file, get_result_file, get_task_file


class _FailingRunner:
    seen_timeout_seconds = None

    async def run(self, context):
        self.seen_timeout_seconds = context.timeout_seconds
        return AgentRunResult(
            status=AgentStatus.FAILED,
            exit_code=1,
            stdout="",
            stderr="You've hit your usage limit. Please try again later.",
            error_message="You've hit your usage limit. Please try again later.",
        )


class _SuccessfulDevRunner:
    async def run(self, context):
        payload = {
            "contract_version": "1.0",
            "generated_at": "2026-03-08T00:00:00Z",
            "constraints_ack": True,
            "module_name": context.module_name or "module_main",
            "status": "success",
            "files_changed": ["app/module_main/main.py"],
            "implementation_notes": "ok",
        }
        return AgentRunResult(
            status=AgentStatus.SUCCESS,
            exit_code=0,
            stdout=json.dumps(payload),
            stderr="",
            error_message=None,
        )


class _WarningNonJsonRunner:
    async def run(self, context):
        return AgentRunResult(
            status=AgentStatus.FAILED,
            exit_code=1,
            stdout="WARNING: proceeding without JSON payload",
            stderr="",
            error_message="Exit code 1: WARNING: proceeding without JSON payload",
        )


@pytest.mark.asyncio
async def test_run_agent_activity_persists_failure_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    monkeypatch.setattr(settings, "agent_max_retries", 2)
    monkeypatch.setattr(settings, "agent_timeout_seconds", 900)
    monkeypatch.setattr(settings, "agent_total_timeout_seconds", 30)
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    monkeypatch.setattr(settings, "codex_agent_max_retries", 0)
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")

    task_file = get_task_file("phase_01", AgentRole.DEV, "module_main")
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text("# dev task", encoding="utf-8")
    runner = _FailingRunner()
    monkeypatch.setattr(activities, "create_runner", lambda: runner)

    result = await activities.run_agent_activity("p1", "phase_01", AgentRole.DEV.value, "module_main")

    assert result["status"] == AgentStatus.FAILED.value
    assert runner.seen_timeout_seconds == 900
    result_file = get_result_file("phase_01", AgentRole.DEV, "module_main")
    assert result_file.exists()
    contract = validate_output_contract(AgentRole.DEV, result_file.read_text(encoding="utf-8"))
    assert contract.status == "failed"
    events = EventStore().read("p1", "phase_01")
    assert any(item.get("event_type") in {"RUNNER_DEGRADED", "STAGE_HARD_FAILED"} for item in events)


def test_non_retryable_error_detection():
    assert activities._is_non_retryable_error("Rate limit exceeded (429)") is True
    assert activities._is_non_retryable_error("generic process error") is False


@pytest.mark.asyncio
async def test_run_agent_activity_soft_fails_when_required_artifact_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")

    acceptance_spec_file = get_contract_file("phase_01", "module_main", "acceptance_spec")
    acceptance_spec_file.parent.mkdir(parents=True, exist_ok=True)
    acceptance_spec_file.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "acceptance_id": "acceptance_phase_01_module_main",
                "task_id": "task_phase_01_module_main",
                "required_tests": ["unit", "integration"],
                "required_graders": ["contract_validator"],
                "required_artifacts": ["app/main/artifacts/phase_01_result.json"],
                "hidden_test_group": "core",
                "rollback_on_failure": True,
                "human_review_required": False,
            }
        ),
        encoding="utf-8",
    )
    task_file = get_task_file("phase_01", AgentRole.DEV, "module_main")
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text("# dev task", encoding="utf-8")
    monkeypatch.setattr(activities, "create_runner", lambda: _SuccessfulDevRunner())

    result = await activities.run_agent_activity("p1", "phase_01", AgentRole.DEV.value, "module_main")

    assert result["status"] == AgentStatus.FAILED.value
    assert result["failure_type"] == "MISSING_DEV_ARTIFACT"
    assert result["failure_severity"] == "soft_fail"
    assert "app/main/artifacts/phase_01_result.json" in result["missing_artifacts"]
    events = EventStore().read("p1", "phase_01")
    assert any(
        item.get("event_type") == "ARTIFACT_MISSING"
        and item.get("failure_type") == "MISSING_DEV_ARTIFACT"
        for item in events
    )


@pytest.mark.asyncio
async def test_run_agent_activity_preserves_last_failure_type_when_retries_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    monkeypatch.setattr(settings, "agent_max_retries", 0)
    monkeypatch.setattr(settings, "agent_runner_type", "codex")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")
    task_file = get_task_file("phase_01", AgentRole.DEV, "module_main")
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text("# dev task", encoding="utf-8")
    monkeypatch.setattr(activities, "create_runner", lambda: _WarningNonJsonRunner())

    result = await activities.run_agent_activity("p2", "phase_01", AgentRole.DEV.value, "module_main")

    assert result["status"] == AgentStatus.FAILED.value
    assert result["failure_type"] == "AGENT_RESULT_PARSE_FAILED"
