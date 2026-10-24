import pytest
from unittest.mock import MagicMock
from quentin.council.done import DoneCouncil

def test_done_council_prompt_contains_test_requirement():
    manager = MagicMock()
    # Capture the prompt passed to run_council
    manager.run_council.return_value = MagicMock(final={"verdict": "undecided"})
    
    council = DoneCouncil(council_manager=manager)
    council.assess(goal={"id": "g1"}, execution_summary={}, metrics={})
    
    prompt = manager.run_council.call_args[0][1].prompt
    assert "TEST EVIDENCE REQUIREMENT" in prompt
    assert "MUST see evidence of a 'pytest' or 's_test' run" in prompt
