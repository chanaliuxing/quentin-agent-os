import pytest
from unittest.mock import MagicMock, AsyncMock
from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask

@pytest.mark.asyncio
async def test_loop_rerun_idempotency(tmp_path, monkeypatch):
    # Disable pre-sensing to avoid extra council calls in this test
    monkeypatch.setenv("QUENTIN_ENABLE_PRE_SENSING", "0")
    
    # Setup
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    council_manager = MagicMock()
    
    # Mocking council calls for 1 full run: Planner, Done Check
    plan_json = '{"answer": {"steps": [{"step_id": "s1", "description": "test", "fingerprint": "f1"}]}, "verdict": "done"}'
    
    m_plan = MagicMock()
    m_plan.final = {"answer": plan_json, "verdict": "done"}
    
    m_done = MagicMock()
    m_done.final = {"verdict": "done", "is_done": True, "reasoning": "ok"}
    
    council_manager.run_council.side_effect = [m_plan, m_done] * 10
    
    # Mock memory_fabric to avoid summarize_history
    memory_fabric = MagicMock()
    memory_fabric.recall.return_value = []
    
    loop = CognitiveLoop(repo_root=str(repo_root), council_manager=council_manager, memory_fabric=memory_fabric, perception_layer=None)
    # Mock internal methods
    loop._get_environment_snapshot = MagicMock(return_value="tree")
    
    # Mock the WHOLE executor call in loop to avoid complex executor internal mocking
    loop._run_executor_or_custom = AsyncMock(return_value={
        "final_output": "ok",
        "actions_summary": "did s1",
        "raw": {"success": True, "steps": [{"step_id": "s1", "fingerprint": "f1", "success": True}]}
    })
    
    # Also need to mock tool_manager.call_tool for direct access check if needed
    loop.executor.tool_manager.call_tool = AsyncMock(return_value=MagicMock(output={"result": "ok"}, success=True))
    
    task = CognitiveTask(input_text="task")
    
    # 1. First run
    await loop._run_goal_internal(task)
    assert loop._run_executor_or_custom.call_count == 1
    
    # 2. Second run
    await loop._run_goal_internal(task)
    assert loop._run_executor_or_custom.call_count == 2
