import pytest
from unittest.mock import MagicMock, AsyncMock
from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask

@pytest.mark.asyncio
async def test_semantic_pre_sensing_already_done():
    # Mock dependencies
    council_manager = MagicMock()
    # Pre-sensing council returns already_done with required fields
    mock_decision = MagicMock()
    mock_decision.final = {
        "verdict": "already_done",
        "confidence": 0.9,
        "evidence_summary": "Files already exist"
    }
    council_manager.run_council.return_value = mock_decision
    
    loop = CognitiveLoop(repo_root=".", council_manager=council_manager)
    # Mock environment snapshot and other blocking calls
    loop._get_environment_snapshot = MagicMock(return_value="file tree")
    loop._ensure_goal = MagicMock(return_value=MagicMock(goal_id="g1"))
    loop.memory_fabric = MagicMock()
    loop.memory_fabric.recall.return_value = []
    loop.trace_recorder = MagicMock()
    
    task = CognitiveTask(input_text="Create a file named test.py")
    
    result = await loop._run_goal_internal(task)
    
    assert result.done is True
    assert "already satisfied" in result.final_output
    assert result.self_awareness.get("idempotent_hit") is True
    # Observability: early-exit still emits trace events (decision/summary)
    assert loop.trace_recorder.record_event.called
