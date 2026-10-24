
import pytest
import os
from unittest.mock import MagicMock, AsyncMock
from quentin.execution.executor import Executor
from quentin.planning import PlanStep

@pytest.mark.asyncio
async def test_executor_auto_fingerprint_skip():
    # Setup
    recorder = MagicMock()
    tm = MagicMock()
    tm.call_tool = AsyncMock(return_value=MagicMock(output={"status": "ok"}, success=True))
    
    executor = Executor(tool_manager=tm, llm=MagicMock(), trace_recorder=recorder, repo_root=".")
    
    executor.idempotency_gate.check = MagicMock(side_effect=[False, True])
    
    # Mutating step without fingerprint
    step = PlanStep(
        step_id="s1",
        description="create dir",
        kind="tool",
        name="mkdir",
        args={"path": "new_dir_test_auto"}
    )
    
    # First execution
    res1 = await executor._execute_step(step, {}, "t1")
    assert res1.get("status") != "skipped"
    
    # Verify fingerprint was generated
    assert step.fingerprint is not None
    f1 = step.fingerprint
    
    # Second execution of identical step
    step2 = PlanStep(
        step_id="s1",
        description="create dir",
        kind="tool",
        name="mkdir",
        args={"path": "new_dir_test_auto"}
    )
    step2.fingerprint = f1
    
    res2 = await executor._execute_step(step2, {}, "t2")
    assert res2.get("status") == "skipped"
    assert res2.get("idempotent_hit") is True

@pytest.mark.asyncio
async def test_executor_auto_fingerprint_content_aware():
    executor = Executor(tool_manager=MagicMock(), llm=MagicMock(), trace_recorder=MagicMock())
    
    s1 = PlanStep(step_id="s1", description="w", kind="tool", name="fs.write_file", args={"path": "a.txt", "content": "v1"})
    s2 = PlanStep(step_id="s2", description="w", kind="tool", name="fs.write_file", args={"path": "a.txt", "content": "v1"})
    s3 = PlanStep(step_id="s3", description="w", kind="tool", name="fs.write_file", args={"path": "a.txt", "content": "v2"})
    
    f1 = executor._generate_auto_fingerprint(s1)
    f2 = executor._generate_auto_fingerprint(s2)
    f3 = executor._generate_auto_fingerprint(s3)
    
    assert f1 == f2
    assert f1 != f3
