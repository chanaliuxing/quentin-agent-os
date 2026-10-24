# tests/integration/test_done_council_end_signal_pipeline.py
import pytest
from unittest.mock import MagicMock
from quentin.council.done import DoneCouncil
from quentin.council.manager import CouncilDecision

def test_done_council_is_done_flow():
    mock_mgr = MagicMock()
    # Mocking a successful "done" decision
    mock_mgr.run_council.return_value = CouncilDecision(
        council_name="done",
        topic="done_check",
        final={"verdict": "done", "is_done": True, "reasoning": "Goal achieved."},
        member_replies=[],
        arbiter_raw="{}",
        created_at="2026-02-14T00:00:00Z"
    )
    
    council = DoneCouncil(council_manager=mock_mgr)
    decision = council.assess(goal={"title": "Test Goal"}, execution_summary={}, metrics={})
    
    assert decision.is_done is True
    assert decision.verdict == "done"
    assert "Goal achieved" in decision.reason

def test_done_council_timeout_fallback_logic():
    # If the council fails or arbiter times out (simplified here by returning specific final)
    mock_mgr = MagicMock()
    
    # Simulate a "weak reasoning" that triggers a retry
    mock_mgr.run_council.side_effect = [
        CouncilDecision(
            council_name="done",
            topic="done_check",
            final={"verdict": "not_done", "reasoning": "too short"},
            member_replies=[],
            arbiter_raw="{}",
            created_at="2026-02-14T00:00:00Z"
        ),
        CouncilDecision(
            council_name="done",
            topic="done_check",
            final={"verdict": "not_done", "reasoning": "still weak"},
            member_replies=[],
            arbiter_raw="{}",
            created_at="2026-02-14T00:00:00Z"
        )
    ]
    
    council = DoneCouncil(council_manager=mock_mgr)
    # This should trigger retry and then fallback to _derive_evidence_reason
    decision = council.assess(
        goal={"title": "Test Goal"}, 
        # Including "failed" to trigger the derive_evidence_reason path
        execution_summary={"final_output": "The task failed at the final step."}, 
        metrics={}
    )
    
    assert decision.is_done is False # Verdict from council was not_done
    assert "council_quality_fallback" in decision.reason
    assert "final_output indicates failure" in decision.reason
    assert "task failed" in decision.reason.lower()
