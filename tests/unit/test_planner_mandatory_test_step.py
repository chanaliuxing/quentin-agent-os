import pytest
from unittest.mock import MagicMock
from quentin.planning.hierarchical_planner import HierarchicalPlanner

@pytest.mark.asyncio
async def test_planner_prompt_contains_mandatory_verification():
    llm = MagicMock()
    # Capture the prompt passed to llm.complete
    llm.complete.return_value = '{"steps": []}'
    
    planner = HierarchicalPlanner(llm=llm, skill_registry=MagicMock())
    await planner.plan("Update logic in core.py", {"domain": "core"})
    
    prompt = llm.complete.call_args[0][0]
    assert "CRITICAL: If the goal involves modifying files" in prompt
    assert "MUST include a final verification step" in prompt
