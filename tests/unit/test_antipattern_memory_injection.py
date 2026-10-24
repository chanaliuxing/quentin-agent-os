import pytest
from unittest.mock import MagicMock
from quentin.council.done import DoneCouncil

def test_done_council_records_antipattern():
    memory = MagicMock()
    manager = MagicMock()
    # Mock a weak reasoning response
    manager.run_council.return_value = MagicMock(final={"verdict": "undecided", "reasoning": "unclear"})
    
    council = DoneCouncil(council_manager=manager, memory_fabric=memory)
    
    # Assess will trigger retry due to weak reasoning
    council.assess(goal={"id": "g1"}, execution_summary={}, metrics={})
    
    # Verify memory.remember_atomic was called with ANTI-PATTERN
    assert memory.remember_atomic.call_count >= 1
    args = memory.remember_atomic.call_args[1]
    assert "ANTI-PATTERN" in args["content"]
    assert "weak_reasoning" in args["tags"]
