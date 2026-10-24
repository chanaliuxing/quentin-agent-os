import pytest
import json
import os
from unittest.mock import MagicMock, patch
from pathlib import Path

from quentin.bootstrap.container import Container
from quentin.tools.manager import ToolManager, ToolCallRequest, ToolCallContext
from quentin.cognitive.contract import RequirementContractor
from quentin.planning.hierarchical_planner import HierarchicalPlanner
from quentin.tools.packs.coder_pack import CoderToolPack

@pytest.fixture
def anyio_backend():
    return 'asyncio'

# 1. Unit Tests for CoderToolPack
def test_coder_tool_pack_registration():
    """Verify that CoderToolPack defines the expected tools."""
    pack = CoderToolPack()
    tools = pack.get_tools()
    tool_names = [t[0].name for t in tools]
    
    assert "coder.generate" in tool_names
    assert "gemini.code" in tool_names
    assert "claude.code" in tool_names

@pytest.mark.anyio
async def test_coder_generate_invocation():
    """Test calling coder.generate through ToolManager with a mock backend."""
    container = Container()
    tm = container.tool_manager
    
    with patch("meta_agent.tools.coder.router.coder_router.generate") as mock_gen:
        mock_gen.return_value = MagicMock(success=True, code="print('hello')", reasoning="mocked")
        
        req = ToolCallRequest(
            tool_name="coder.generate",
            payload={
                "goal": "test goal",
                "instructions": "test inst",
                "backend": "gemini_cli"
            }
        )
        ctx = ToolCallContext(metadata={"session_id": "test_session"})
        
        result = await tm.call_tool(req, ctx)
        
        assert result.success is True
        assert result.output["code"] == "print('hello')"
        assert mock_gen.called

# 2. Regression Tests
def test_tool_manager_regression():
    """Ensure standard tools like fs.read_file are still available and unaffected."""
    container = Container()
    tm = container.tool_manager
    tools = tm.list_tool_names()
    
    assert "fs.read_file" in tools
    assert "shell.run_command" in tools
    assert "ls" in tools

def test_contract_regression():
    """Verify that RequirementContractor still classifies basic tasks correctly."""
    contractor = RequirementContractor(repo_root=Path("."))
    # 'analyze' triggers 'research' domain
    contract = contractor.build_contract("analyze the codebase", "t1", {})
    
    assert contract.domain == "research"
    assert contract.intent == "analysis"

# 3. New Intelligence Tests (Mental Model Evolution)
def test_contract_coding_preference():
    """Verify that the brain's mental model now includes a preference for coding tools."""
    contractor = RequirementContractor(repo_root=Path("."))
    # Task involving 'fix' should trigger the new constraint
    contract = contractor.build_contract("fix the bug in logic.py", "t2", {"files": [{"path": "logic.py"}]})
    
    found_tool_constraint = False
    for c in contract.constraints:
        if "coder.generate" in c or "gemini.code" in c:
            found_tool_constraint = True
            break
    
    assert found_tool_constraint is True, "Mental model should suggest specialized coding tools for 'fix' tasks."

@pytest.mark.anyio
async def test_planner_coding_skill_visibility():
    """Verify that the planner's prompt includes the new coding skills."""
    container = Container()
    # HierarchicalPlanner uses the skill registry to list skills
    planner = container.cognitive_loop.council_manager.run_council # Accessing via loop
    
    # We'll check the registry directly as a proxy for planner visibility
    registry = container.skill_manager.backend_registry
    skills = []
    for backend in registry.list_backends():
        skills.extend(backend.list_skills())
    
    skill_ids = [s.id for s in skills]
    assert "coder.generate" in skill_ids
    assert "gemini.code" in skill_ids

# 4. Backend Logic Tests (Regression for path handling)
def test_gemini_backend_prompt_builder():
    """Test that the Gemini backend correctly builds a prompt with context files."""
    from meta_agent.tools.coder.gemini_cli_backend import GeminiCliBackend
    from meta_agent.tools.coder.base import CodeGenerationRequest
    
    backend = GeminiCliBackend()
    # Mock a file on disk
    test_file = Path("mutable/test_context.py")
    test_file.write_text("print('old code')", encoding="utf-8")
    
    req = CodeGenerationRequest(
        goal="refactor",
        instructions="make it faster",
        context_files=[str(test_file)]
    )
    
    prompt = backend._build_prompt(req)
    assert "print('old code')" in prompt
    assert "refactor" in prompt
    
    # Cleanup
    if test_file.exists(): test_file.unlink()

if __name__ == "__main__":
    # If run directly, execute with pytest
    import sys
    sys.exit(pytest.main([__file__]))
