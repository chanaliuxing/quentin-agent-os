import pytest
from unittest.mock import AsyncMock, MagicMock
from quentin.bootstrap.container import Container
from quentin.planning import Plan, PlanStep

@pytest.mark.asyncio
async def test_executor_idempotent_rerun(tmp_path):
    # Setup a mock repo root
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    
    # Define a step with a fingerprint
    step = PlanStep(
        step_id="step1",
        description="test action",
        kind="tool",
        name="shell.run_command",
        args={"command": "echo 'hello'"},
        fingerprint="unique-fp-123"
    )
    plan = Plan(plan_id="p1", goal="test", steps=[step])
    
    # Mock tool manager to track calls
    executor.tool_manager.call_tool = AsyncMock(return_value=MagicMock(output={"result": "ok"}, success=True))
    
    # 1. First execution
    await executor.execute_plan(plan, {"domain": "core", "environment": "sandbox"})
    assert executor.tool_manager.call_tool.call_count == 1
    
    # 2. Second execution with same fingerprint
    await executor.execute_plan(plan, {"domain": "core", "environment": "sandbox"})
    
    # Should NOT call tool again due to idempotency
    assert executor.tool_manager.call_tool.call_count == 1
