import pytest
from unittest.mock import AsyncMock, MagicMock
from quentin.bootstrap.container import Container
from quentin.planning import Plan, PlanStep

@pytest.mark.asyncio
async def test_step_contract_violation_strict(tmp_path, monkeypatch):
    monkeypatch.setenv("QUENTIN_STRICT_STEP_CONTRACT", "1")
    
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    
    # Plan with mutation but no prior observation
    step = PlanStep(
        step_id="s1",
        description="write file",
        kind="tool",
        name="fs.write_file",
        args={"path": "test.py", "content": "hi"}
    )
    plan = Plan(plan_id="p1", goal="test", steps=[step])
    
    with pytest.raises(RuntimeError, match="violated step contract"):
        await executor.execute_plan(plan, {})

@pytest.mark.asyncio
async def test_step_contract_alignment_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("QUENTIN_STRICT_STEP_CONTRACT", "1")
    
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    executor.tool_manager.call_tool = AsyncMock(return_value=MagicMock(output={"result": "ok"}, success=True))
    
    # Plan with observation then mutation
    s1 = PlanStep(step_id="s1", description="read", kind="tool", name="fs.read_file", args={"path": "test.py"})
    s2 = PlanStep(step_id="s2", description="write", kind="tool", name="fs.write_file", args={"path": "test.py"})
    plan = Plan(plan_id="p1", goal="test", steps=[s1, s2])
    
    # Should pass
    await executor.execute_plan(plan, {})
    assert executor.tool_manager.call_tool.call_count == 2
