import pytest
from pathlib import Path
from app.models import ProjectState, AgentRole
from app.graph import create_autoloop_graph
from app.utils import ensure_phase_dirs


@pytest.mark.asyncio
async def test_langgraph_workflow_basic(mock_settings, sample_prd):
    graph = create_autoloop_graph()

    initial_state = ProjectState(project_id="test-project", prd_path=str(sample_prd))

    result = await graph.ainvoke(initial_state)
    if isinstance(result, dict):
        result = ProjectState.model_validate(result)

    assert result.project_id == "test-project"
    assert result.current_phase >= 1
    assert len(result.phases) >= 1


@pytest.mark.asyncio
async def test_temporal_mock_workflow(mock_settings, sample_prd):
    from app.temporal.mock_worker import MockTemporalWorker

    worker = MockTemporalWorker()

    result = await worker.run_workflow("test-project", str(sample_prd))

    assert result["project_id"] == "test-project"
    assert result["phase_id"] == "phase_01"
    assert result["status"] == "completed"
    assert result["acceptance_status"] == "passed"
    assert result["recommended_action"] == "advance"
    assert result.get("human_review_hook", "") == ""
    assert "phase_report" in result
    assert "evidence_file" in result
    assert Path(result["evidence_file"]).exists()
    assert "energy" in result
    assert "decision" in result
    assert "energy_history" in result
    assert "repair_history" in result
    assert "repair_execution_history" in result


@pytest.mark.asyncio
async def test_phase_directory_creation(mock_settings):
    phase_id = "phase_01"
    ensure_phase_dirs(phase_id)

    from app.utils.file_utils import get_phase_dir

    phase_dir = get_phase_dir(phase_id)
    assert phase_dir.exists()
    assert (phase_dir / "tasks").exists()
    assert (phase_dir / "results").exists()
