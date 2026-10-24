import pytest
from unittest.mock import MagicMock
from quentin.council.done import DoneCouncil

def test_done_council_blocks_without_test_evidence():
    manager = MagicMock()
    # Mock arbiter reasoning that does NOT contain test evidence
    manager.run_council.return_value = MagicMock(final={
        "verdict": "done", 
        "reasoning": "I wrote the file and it looks good.",
        "is_done": True
    })
    
    # We need to pass a mock memory_fabric now
    council = DoneCouncil(council_manager=manager, memory_fabric=MagicMock())
    # Execution summary indicates a write happened (e.g. by tool name in actions_summary)
    exec_summary = {"actions_summary": "fs.write_file: test.py", "final_output": "Done"}
    
    decision = council.assess(goal={"id": "g1"}, execution_summary=exec_summary, metrics={})
    
    # Verify the prompt passed to manager included the TEST EVIDENCE rule
    prompt = manager.run_council.call_args[0][1].prompt
    assert "TEST EVIDENCE REQUIREMENT" in prompt
