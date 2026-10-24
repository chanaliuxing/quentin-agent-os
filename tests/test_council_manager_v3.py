import pytest
import json
from unittest.mock import MagicMock
from collections import deque

from quentin.council.manager import CouncilManager, CouncilConfig, CouncilQuestion, CouncilMemberConfig, DiscussionRound
from quentin.council.schema import ModeratorOutput, MemberReply, NextQuestion
from quentin.llm import client as llm_client

# --- Fake LLM Setup ---
class FakeLLM:
    def __init__(self, responses):
        self.responses = deque(responses)

    async def generate(self, *args, **kwargs):
        if not self.responses:
            raise Exception("No more fake LLM responses!")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

def fake_call_llm_factory(responses_list):
    """Creates a callable that can be monkey-patched into llm_client.call_llm"""
    current_response_idx = 0

    async def _fake_call_llm(cfg, user_prompt, system_prompt):
        nonlocal current_response_idx
        if current_response_idx >= len(responses_list):
            raise Exception(f"FakeLLM exhausted at index {current_response_idx}, add more responses to responses_list")

        response = responses_list[current_response_idx]
        current_response_idx += 1

        if callable(response):
            return await response(cfg, user_prompt, system_prompt)
        return response
    return _fake_call_llm

@pytest.fixture
def mock_council_manager():
    """Fixture to create a CouncilManager with a basic config."""
    member_config = CouncilMemberConfig(
        member_id="test_member",
        router_mode="test_mode",
        router_task_type="test_task"
    )
    council_cfg = CouncilConfig(
        name="test_council",
        description="A test council",
        members=[member_config],
        decision_mode="moderator_v2",
        max_rounds=5,
        stall_rounds=2,
        summary_max_chars=1000,
        moderator_router_mode="test_mode",
        moderator_router_task_type="moderator"
    )
    # Mock the internal _councils dict
    manager = CouncilManager(repo_root=".")
    manager._councils = {"test_council": council_cfg}
    
    # Mock router.route method to return a dummy config for now
    manager.model_router.route = MagicMock(return_value={
        "name": "mock_model",
        "base_url": "http://mock-llm:11434",
        "model": "qwen2.5vl:latest"
    })
    return manager

@pytest.fixture
def mock_question():
    """Fixture for a basic CouncilQuestion."""
    return CouncilQuestion(
        topic="test_topic",
        importance="normal",
        prompt="Please decide on this test proposal.",
        payload={"proposal": "do something"}
    )

# UT-01: Single-round approve
@pytest.mark.asyncio
async def test_ut01_single_round_approve(monkeypatch, mock_council_manager, mock_question):
    responses = [
        json.dumps({
            "verdict": "approve",
            "reasoning": "All members agree.",
            "open_issues": [],
            "next_round_plan": [],
            "current_summary": "All agreed.",
            "progress_notes": ["Consensus reached"],
            "resolved_issues": [],
            "newly_added_issues": [],
            "confidence": 0.5,
            "final_answer": {"result": "OK"}
        })
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    decision = await mock_council_manager.run_council("test_council", mock_question)

    assert decision.final["verdict"] == "approve"
    assert decision.final["stop_reason"] == "consensus"
    assert decision.final["final_answer"]["result"] == "OK"
    assert len(decision.rounds) == 1

# UT-02: Debate -> Approve (2 rounds)
@pytest.mark.asyncio
async def test_ut02_debate_then_approve(monkeypatch, mock_council_manager, mock_question):
    responses = [
        # Round 1 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Security risk unclear"],
            "next_round_plan": [
                {"target": "test_member", "question": "Is this exploitable?"}
            ],
            "current_summary": "Conflict on security risk.",
            "progress_notes": [],
            "resolved_issues": [],
            "newly_added_issues": [],
            "confidence": 0.5,
            "final_answer": None
        }),
        # Round 1 (Member)
        json.dumps({
            "stance": "neutral",
            "key_points": ["Needs clarification"],
            "raw": "Member response for round 1",
            "confidence": 0.6
        }),
        # Round 2 (Moderator)
        json.dumps({
            "verdict": "approve",
            "reasoning": "Security clarified, safe.",
            "open_issues": [],
            "next_round_plan": [],
            "current_summary": "Security clarified, safe.",
            "progress_notes": ["Security clarified"],
            "resolved_issues": [],
            "newly_added_issues": [],
            "confidence": 0.8,
            "final_answer": {"approved": True}
        }),
         # Round 2 (Member) - This will be called again in round 2 but we only target one member in next_round_plan
         json.dumps({
            "stance": "approve",
            "key_points": ["Exploitable issue resolved"],
            "raw": "Member response for round 2",
            "confidence": 0.9
        }),
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    decision = await mock_council_manager.run_council("test_council", mock_question)

    assert decision.final["verdict"] == "approve"
    assert len(decision.rounds) == 2
    assert decision.final["stop_reason"] == "consensus"
    assert decision.final["final_answer"]["approved"] == True
    # Verify the target for the second round. This requires inspecting the history, which is available in decision.rounds
    # For simplicity, we just assert the overall outcome. More detailed checks would involve mocking member calls separately.

# UT-03: Stall trigger (issues unchanged)
@pytest.mark.asyncio
async def test_ut03_stall_trigger(monkeypatch, mock_council_manager, mock_question):
    # This scenario needs to simulate moderator and member calls for multiple rounds
    # and ensure open_issues remain the same without progress.
    responses = [
        # Round 1 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Unclear ownership"],
            "next_round_plan": [{"target": "test_member", "question": "Clarify ownership"}],
            "current_summary": "Ownership unclear in round 1.",
            "progress_notes": [], "resolved_issues": [], "newly_added_issues": [], "confidence": 0.5, "final_answer": None
        }),
        # Round 1 (Member)
        json.dumps({
            "stance": "neutral",
            "key_points": ["Still unclear"],
            "raw": "Member response round 1",
            "confidence": 0.6
        }),
        # Round 2 (Moderator) - Issues still "Unclear ownership", no progress notes
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Unclear ownership"],
            "next_round_plan": [{"target": "test_member", "question": "Any new info on ownership?"}],
            "current_summary": "Ownership still unclear in round 2.",
            "progress_notes": [], "resolved_issues": [], "newly_added_issues": [], "confidence": 0.5, "final_answer": None
        }),
        # Round 2 (Member)
        json.dumps({
            "stance": "neutral",
            "key_points": ["No new info"],
            "raw": "Member response round 2",
            "confidence": 0.6
        }),
         # Round 3 (Moderator) - Issues still "Unclear ownership", no progress notes, should trigger stall
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Unclear ownership"],
            "next_round_plan": [{"target": "test_member", "question": "Last chance for ownership clarification?"}],
            "current_summary": "Ownership still unclear in round 3.",
            "progress_notes": [], "resolved_issues": [], "newly_added_issues": [], "confidence": 0.5, "final_answer": None
        }),
         # Round 3 (Member)
        json.dumps({
            "stance": "neutral",
            "key_points": ["Still no new info"],
            "raw": "Member response round 3",
            "confidence": 0.6
        }),
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    # Configure the council to have stall_rounds = 2
    mock_council_manager._councils["test_council"].stall_rounds = 2
    mock_council_manager._councils["test_council"].max_rounds = 5


    decision = await mock_council_manager.run_council("test_council", mock_question)
    
    assert decision.final["verdict"] == "revise"
    assert decision.final["stop_reason"] == "stalled"
    assert "needs_revision" in decision.final["final_answer"]["status"]
    assert len(decision.rounds) == 3 # 2 rounds debated, 3rd round triggered stall and forced revise

# UT-04: Max rounds trigger
@pytest.mark.asyncio
async def test_ut04_max_rounds_trigger(monkeypatch, mock_council_manager, mock_question):
    # This scenario simulates continuous debate until max_rounds is reached.
    # We'll make open_issues change each time to prevent stall.
    responses = [
        # Round 1 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Issue 1"],
            "next_round_plan": [{"target": "test_member", "question": "Question 1"}],
            "current_summary": "Summary 1",
            "progress_notes": ["New info 1"], "resolved_issues": [], "newly_added_issues": ["Issue 1"], "confidence": 0.5, "final_answer": None
        }),
        # Round 1 (Member)
        json.dumps({
            "stance": "neutral", "raw": "Member 1 response", "confidence": 0.6
        }),
        # Round 2 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Issue 2"], # Changed issue
            "next_round_plan": [{"target": "test_member", "question": "Question 2"}],
            "current_summary": "Summary 2",
            "progress_notes": ["New info 2"], "resolved_issues": ["Issue 1"], "newly_added_issues": ["Issue 2"], "confidence": 0.5, "final_answer": None
        }),
        # Round 2 (Member)
        json.dumps({
            "stance": "neutral", "raw": "Member 2 response", "confidence": 0.6
        }),
        # Round 3 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Issue 3"], # Changed issue
            "next_round_plan": [{"target": "test_member", "question": "Question 3"}],
            "current_summary": "Summary 3",
            "progress_notes": ["New info 3"], "resolved_issues": ["Issue 2"], "newly_added_issues": ["Issue 3"], "confidence": 0.5, "final_answer": None
        }),
        # Round 3 (Member)
        json.dumps({
            "stance": "neutral", "raw": "Member 3 response", "confidence": 0.6
        }),
        # Round 4 (Moderator)
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Issue 4"], # Changed issue
            "next_round_plan": [{"target": "test_member", "question": "Question 4"}],
            "current_summary": "Summary 4",
            "progress_notes": ["New info 4"], "resolved_issues": ["Issue 3"], "newly_added_issues": ["Issue 4"], "confidence": 0.5, "final_answer": None
        }),
        # Round 4 (Member)
        json.dumps({
            "stance": "neutral", "raw": "Member 4 response", "confidence": 0.6
        }),
        # Round 5 (Moderator) - max_rounds will be reached here
        json.dumps({
            "verdict": "debate",
            "debate_type": "conflict",
            "open_issues": ["Issue 5"], # Changed issue
            "next_round_plan": [{"target": "test_member", "question": "Question 5"}],
            "current_summary": "Summary 5",
            "progress_notes": ["New info 5"], "resolved_issues": ["Issue 4"], "newly_added_issues": ["Issue 5"], "confidence": 0.5, "final_answer": None
        }),
        # Round 5 (Member)
        json.dumps({
            "stance": "neutral", "raw": "Member 5 response", "confidence": 0.6
        }),
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    mock_council_manager._councils["test_council"].max_rounds = 5 # Set max rounds
    mock_council_manager._councils["test_council"].stall_rounds = 10 # Prevent stall trigger


    decision = await mock_council_manager.run_council("test_council", mock_question)
    
    assert decision.final["verdict"] == "revise"
    assert decision.final["stop_reason"] == "max_rounds"
    assert "needs_revision" in decision.final["final_answer"]["status"]
    assert len(decision.rounds) == 5

# UT-05: Bad JSON -> retry -> successful repair
@pytest.mark.asyncio
async def test_ut05_bad_json_then_repair_success(monkeypatch, mock_council_manager, mock_question):
    responses = [
        # Moderator's first attempt: bad JSON (from _moderate_discussion)
        "I cannot give you JSON. This is invalid output. {\"verdict\": \"debate\"", # Missing closing brace
        # Moderator's second attempt (after retry prompt): good JSON (from _moderate_discussion)
        json.dumps({
            "verdict": "approve",
            "reasoning": "JSON successfully repaired.",
            "open_issues": [],
            "next_round_plan": [],
            "current_summary": "Repaired to approve.",
            "progress_notes": [], "resolved_issues": [], "newly_added_issues": [], "confidence": 0.9,
            "final_answer": {"status": "repaired_ok"}
        }),
         # Member call in the successful round (always expected after a successful moderator call if not 'approve')
        json.dumps({
            "stance": "approve", "raw": "Member response after repair", "confidence": 0.7
        }),
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    decision = await mock_council_manager.run_council("test_council", mock_question)

    assert decision.final["verdict"] == "approve"
    assert decision.final["stop_reason"] == "consensus"
    assert decision.final["final_answer"]["status"] == "repaired_ok"
    # Expect 1 round for the actual decision, plus retries for the moderator
    assert len(decision.rounds) == 1

# UT-06: Bad JSON -> repair failure -> forced revise
@pytest.mark.asyncio
async def test_ut06_bad_json_repair_failure_fallback(monkeypatch, mock_council_manager, mock_question):
    responses = [
        # Moderator's first attempt: bad JSON
        "Absolutely no JSON here.",
        # Moderator's second attempt (after retry prompt): still bad JSON
        "Still no JSON. Just text.",
        # Repairer's attempt (if _call_llm_json_with_retry calls it) - also bad
        "Even the repairer failed. Still no JSON.",
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    decision = await mock_council_manager.run_council("test_council", mock_question)

    assert decision.final["verdict"] == "revise"
    assert decision.final["stop_reason"] == "json_error"
    assert "needs_revision" in decision.final["final_answer"]["status"]
    assert "json_error" in decision.final["reasoning"] # Reasoning should indicate JSON error
    assert len(decision.rounds) == 1 # Still one logical round, but internal retries happened

# UT-07: verdict=approve but no final_answer -> invalid output -> retry/repair -> forced revise
@pytest.mark.asyncio
async def test_ut07_approve_no_final_answer_fallback(monkeypatch, mock_council_manager, mock_question):
    responses = [
        # Moderator's output, verdict is approve but no final_answer
        json.dumps({
            "verdict": "approve",
            "reasoning": "Consensus reached but forgot final answer.",
            "open_issues": [],
            "next_round_plan": [],
            "current_summary": "Forgot answer.",
            "progress_notes": [], "resolved_issues": [], "newly_added_issues": [], "confidence": 0.7,
            "final_answer": None # This should trigger validation error in Pydantic model
        }),
        # In this specific test, the initial moderator response is valid JSON, but fails Pydantic validation (because final_answer is None for non-debate verdict)
        # The manager's _moderate_discussion catches this and forces a revise.
    ]
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm_factory(responses))

    decision = await mock_council_manager.run_council("test_council", mock_question)

    assert decision.final["verdict"] == "revise"
    assert decision.final["stop_reason"] == "json_error" # The forced revise happens due to Pydantic validation failure, which is treated as a JSON error here.
    assert "needs_revision" in decision.final["final_answer"]["status"]
    assert "ModeratorOutput validation failed" in decision.final["reasoning"]
    assert len(decision.rounds) == 1
