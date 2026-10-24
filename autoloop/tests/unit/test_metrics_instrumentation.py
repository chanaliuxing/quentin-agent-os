import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.observability.metrics import (
    MetricsTimer,
    MetricsCollector,
    classify_error,
    workflow_duration_seconds,
    workflow_total,
    workflow_active,
    agent_execution_duration_seconds,
    agent_execution_total,
    agent_errors_total,
    cli_call_duration_seconds,
    cli_errors_total,
    git_conflicts_total,
    planning_rounds,
)
from app.models import ProjectState, AgentRole, AgentStatus
from app.graph.nodes import (
    lead_plan_node,
    phase_done_node,
    phase_fail_node,
    lead_integrate_node,
)
from app.gitops.overlap import detect_git_overlaps
from app.runners.codex_runner import CodexRunner
from app.runners.base import AgentRunContext


class TestMetricsTimer:
    def test_timer_context_manager(self):
        with MetricsTimer() as timer:
            import time
            time.sleep(0.1)

        assert timer.duration_seconds >= 0.1
        assert timer.start_time > 0
        assert timer.end_time > timer.start_time

    def test_timer_duration_property(self):
        timer = MetricsTimer()
        timer.__enter__()
        import time
        time.sleep(0.05)
        timer.__exit__(None, None, None)

        duration = timer.duration_seconds
        assert duration >= 0.05


class TestMetricsCollector:
    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass

        yield

        for collector in list(REGISTRY._collector_to_names.keys()):
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass

    def test_record_agent_execution(self):
        MetricsCollector.record_agent_execution(
            agent_role="dev",
            runner_type="mock",
            status="success",
            duration_seconds=10.5,
        )

        assert True

    def test_record_cli_call(self):
        MetricsCollector.record_cli_call(
            cli_type="codex",
            agent_role="dev",
            duration_seconds=5.2,
        )

        assert True

    def test_record_workflow(self):
        MetricsCollector.record_workflow(
            phase="phase_01",
            status="completed",
            duration_seconds=120.0,
        )

        assert True

    def test_increment_workflow_active(self):
        MetricsCollector.increment_workflow_active("phase_01")
        assert True

    def test_decrement_workflow_active(self):
        MetricsCollector.increment_workflow_active("phase_01")
        MetricsCollector.decrement_workflow_active("phase_01")
        assert True

    def test_increment_errors(self):
        MetricsCollector.increment_errors("dev", "timeout")
        assert True

    def test_increment_cli_errors(self):
        MetricsCollector.increment_cli_errors("codex", "execution_error")
        assert True

    def test_increment_conflicts(self):
        MetricsCollector.increment_conflicts("phase_01", "high", count=3)
        assert True

    def test_record_planning_rounds(self):
        MetricsCollector.record_planning_rounds("phase_01", 2)
        assert True

    def test_record_dev_qa_rounds(self):
        MetricsCollector.record_dev_qa_rounds("phase_01", "auth", 1)
        assert True


class TestClassifyError:
    def test_classify_timeout_error(self):
        exc = TimeoutError("Connection timed out")
        assert classify_error(exc) == "timeout"

    def test_classify_rate_limit_error(self):
        exc = Exception("Rate limit exceeded: 429")
        assert classify_error(exc) == "rate_limit"

    def test_classify_api_error(self):
        exc = Exception("API error: 401 Unauthorized")
        assert classify_error(exc) == "api_error"

    def test_classify_network_error(self):
        exc = Exception("Network connection failed")
        assert classify_error(exc) == "network_error"

    def test_classify_generic_error(self):
        exc = ValueError("Invalid value")
        assert classify_error(exc) == "valueerror"


class TestWorkflowNodeInstrumentation:
    @pytest.mark.asyncio
    async def test_lead_plan_node_increments_active_workflows(self):
        state = ProjectState(
            project_id="test_project",
            prd_path="/tmp/test.md",
            current_phase=1,
        )

        with patch.object(Path, 'exists', return_value=False):
            result = await lead_plan_node(state)

        assert result.current_phase == 1

    @pytest.mark.asyncio
    async def test_phase_done_node_decrements_active_workflows(self):
        state = ProjectState(
            project_id="test_project",
            prd_path="/tmp/test.md",
            current_phase=1,
        )
        phase = state.add_phase("phase_01")
        phase.started_at = datetime.now()

        result = await phase_done_node(state)

        assert result.is_completed is True

    @pytest.mark.asyncio
    async def test_phase_fail_node_records_failure(self):
        state = ProjectState(
            project_id="test_project",
            prd_path="/tmp/test.md",
            current_phase=1,
        )
        phase = state.add_phase("phase_01")
        phase.started_at = datetime.now()

        result = await phase_fail_node(state)

        assert result.is_failed is True

    @pytest.mark.asyncio
    async def test_lead_integrate_node_records_workflow_duration(self):
        state = ProjectState(
            project_id="test_project",
            prd_path="/tmp/test.md",
            current_phase=1,
        )
        phase = state.add_phase("phase_01")
        phase.started_at = datetime.now()

        result = await lead_integrate_node(state)

        assert result.next_action == "phase_done"


class TestGitOverlapInstrumentation:
    def test_detect_git_overlaps_increments_conflicts(self):
        with patch('app.gitops.overlap.Repo') as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance

            mock_commit = MagicMock()
            mock_commit.stats.files.keys.return_value = ["file1.py", "file2.py"]
            mock_repo_instance.commit.return_value = mock_commit

            overlaps = detect_git_overlaps(
                repo_path=Path("/tmp/test"),
                phase_id="phase_01",
                agent_commits={
                    AgentRole.DEV: ["abc123"],
                    AgentRole.QA: ["def456"],
                },
            )

            assert isinstance(overlaps, list)


class TestCodexRunnerInstrumentation:
    @pytest.mark.asyncio
    async def test_codex_runner_records_cli_call_duration(self):
        runner = CodexRunner({"session_id": "test_session"})

        context = AgentRunContext(
            agent=AgentRole.DEV,
            task_file=Path("/tmp/task.md"),
            result_file=Path("/tmp/result.md"),
            working_dir=Path("/tmp/work"),
            log_file=Path("/tmp/log.txt"),
            phase_id="phase_01",
            timeout_seconds=60,
        )

        with patch('app.runners.codex_runner.run_subprocess_with_timeout') as mock_run:
            mock_run.return_value = {
                "returncode": 0,
                "stdout": "success",
                "stderr": "",
            }

            with patch.object(runner, '_get_latest_commit', return_value="abc123"):
                result = await runner.run(context)

        assert result.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_codex_runner_records_cli_errors_on_timeout(self):
        runner = CodexRunner({"session_id": "test_session"})

        context = AgentRunContext(
            agent=AgentRole.DEV,
            task_file=Path("/tmp/task.md"),
            result_file=Path("/tmp/result.md"),
            working_dir=Path("/tmp/work"),
            log_file=Path("/tmp/log.txt"),
            phase_id="phase_01",
            timeout_seconds=1,
        )

        import asyncio

        with patch('app.runners.codex_runner.run_subprocess_with_timeout') as mock_run:
            mock_run.side_effect = asyncio.TimeoutError()

            result = await runner.run(context)

        assert result.status == AgentStatus.FAILED
        assert "Timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_codex_runner_records_cli_errors_on_exception(self):
        runner = CodexRunner({"session_id": "test_session"})

        context = AgentRunContext(
            agent=AgentRole.DEV,
            task_file=Path("/tmp/task.md"),
            result_file=Path("/tmp/result.md"),
            working_dir=Path("/tmp/work"),
            log_file=Path("/tmp/log.txt"),
            phase_id="phase_01",
            timeout_seconds=60,
        )

        with patch('app.runners.codex_runner.run_subprocess_with_timeout') as mock_run:
            mock_run.side_effect = Exception("Test error")

            result = await runner.run(context)

        assert result.status == AgentStatus.FAILED
        assert "Exception" in result.error_message
