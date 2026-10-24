import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from quentin.bootstrap.container import Container
from quentin.planning import Plan, PlanStep
from quentin.tools.schemas import ToolSpec

@pytest.mark.asyncio
async def test_quality_gate_interception(tmp_path, monkeypatch):
    monkeypatch.setenv("QUENTIN_TOOL_MIDDLEWARE_PIPELINE", "1")
    monkeypatch.setenv("QUENTIN_QUALITY_GATE_RULES", "ALL")
    
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "config").mkdir()
    (repo_root / "data").mkdir()
    (repo_root / "mutable").mkdir()
    
    container = Container(repo_root=str(repo_root))
    executor = container.executor
    
    # Tool manager should actually write the file for ruff to check it
    from quentin.tools.filesystem import fs_write_file, fs_read_file
    from quentin.tools.shell import shell_run_command
    
    write_spec = ToolSpec(name="fs.write_file", description="write", domain="fs")
    read_spec = ToolSpec(name="fs.read_file", description="read", domain="fs")
    ls_spec = ToolSpec(name="shell.run_command", description="run", domain="shell")
    
    executor.tool_manager.register_tool(write_spec, fs_write_file)
    executor.tool_manager.register_tool(read_spec, fs_read_file)
    executor.tool_manager.register_tool(ls_spec, shell_run_command)
    # Register ls alias
    executor.tool_manager.register("ls", shell_run_command)
    
    # Pre-create the file to satisfy contract
    (repo_root / "mutable" / "broken.py").write_text("# empty")

    # 1. Observe first to satisfy contract.
    obs_step = PlanStep(
        step_id="s0",
        description="read file",
        kind="tool",
        name="fs.read_file",
        args={"path": "mutable/broken.py"}
    )
    
    # 2. Write broken python code
    # We use unused import which should definitely be caught by ruff check --select ALL
    step = PlanStep(
        step_id="s1",
        description="write broken code",
        kind="tool",
        name="fs.write_file",
        args={"path": "mutable/broken.py", "content": "import os\n"} 
    )
    
    await executor._execute_step(obs_step, {}, "t0")
    
    # We expect RuntimeError from QualityGate if ruff finds errors.
    with pytest.raises(RuntimeError, match="Quality gate failed"):
        await executor._execute_step(step, {}, "t1")
    
    # File should exist but result was success=False due to gate
    assert (repo_root / "mutable" / "broken.py").exists()
