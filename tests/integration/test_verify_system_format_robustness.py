import pytest
from unittest.mock import AsyncMock, MagicMock
from quentin.bootstrap.container import Container
from quentin.planning import PlanStep

@pytest.mark.asyncio
async def test_executor_format_robustness(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    
    messy_json = """
Certainly! Here is the JSON you requested:
```json
{"status": "ok", "result": "salvaged"}
```
I hope this helps!
"""
    executor.llm.complete = MagicMock(return_value=messy_json)
    
    step = PlanStep(step_id="s1", description="test", kind="llm_call", name="direct", args={})
    
    # Capture trace events
    events = []
    executor.trace_recorder.record_event = lambda e: events.append(e)
    
    await executor._execute_step(step, {}, "t1")
    
    # Find the step_end event
    end_event = next(e for e in events if e.payload.get("phase") == "step_end")
    assert end_event.payload["output"] == {"status": "ok", "result": "salvaged"}
    assert end_event.payload["format_salvaged"] is True
