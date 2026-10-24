import pytest
from unittest.mock import MagicMock, AsyncMock
from quentin.execution.executor import Executor
from quentin.planning import PlanStep

@pytest.mark.asyncio
async def test_executor_fast_path_trigger():
    recorder = MagicMock()
    executor = Executor(tool_manager=MagicMock(), llm=MagicMock(), trace_recorder=recorder)
    
    # ls is a fast path tool
    step = PlanStep(step_id="s1", description="list files", kind="tool", name="ls", args={})
    
    # Capture events
    events = []
    recorder.record_event = lambda e: events.append(e)
    
    # We mock tool manager to not actually call anything. Must be AsyncMock because it's awaited.
    executor.tool_manager.call_tool = AsyncMock(return_value=MagicMock(output={"result": "."}, success=True))
    
    await executor._execute_step(step, {}, "t1")
    
    # Verify fast_path event was recorded
    assert any(e.payload.get("phase") == "fast_path" for e in events)
