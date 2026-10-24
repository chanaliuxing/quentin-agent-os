import pytest
from unittest.mock import AsyncMock, MagicMock
from quentin.bootstrap.container import Container
from quentin.planning import PlanStep

@pytest.mark.asyncio
async def test_fast_path_latency_benefit(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    
    # 1. Normal Path (e.g. fs.write_file)
    normal_step = PlanStep(step_id="s1", description="write", kind="tool", name="fs.write_file", args={"path": "test.txt"})
    
    # 2. Fast Path (e.g. ls)
    fast_step = PlanStep(step_id="s2", description="list", kind="tool", name="ls", args={})
    
    # Mock tool manager
    executor.tool_manager.call_tool = AsyncMock(return_value=MagicMock(output={"result": "ok"}, success=True))
    
    # Capture trace events
    events = []
    executor.trace_recorder.record_event = lambda e: events.append(e)
    
    await executor._execute_step(normal_step, {}, "t1")
    assert not any(e.payload.get("phase") == "fast_path" for e in events)
    
    events.clear()
    await executor._execute_step(fast_step, {}, "t2")
    assert any(e.payload.get("phase") == "fast_path" for e in events)
