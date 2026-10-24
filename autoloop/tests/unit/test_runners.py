import json
import pytest
from pathlib import Path
from app.models import AgentRole, AgentStatus
from app.runners import MockRunner, AgentRunContext


@pytest.mark.asyncio
async def test_mock_runner_health_check():
    runner = MockRunner()
    health = await runner.health_check()
    assert health is True


@pytest.mark.asyncio
async def test_mock_runner_execution(mock_settings, temp_project_dir):
    runner = MockRunner()

    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "log.txt"

    task_file.write_text("# Test Task")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.exit_code == 0
    assert result.duration_seconds > 0
    assert result_file.exists()
    payload = json.loads(result_file.read_text())
    assert payload["contract_version"] == "1.0"
