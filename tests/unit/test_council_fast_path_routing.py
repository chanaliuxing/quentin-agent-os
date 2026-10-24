import pytest
from unittest.mock import MagicMock
from quentin.council.manager import CouncilManager, CouncilQuestion, CouncilConfig, CouncilMemberConfig

def test_council_fast_path_low_importance():
    model_router = MagicMock()
    model_router.route.return_value = MagicMock(provider="ollama", name="test")
    
    manager = CouncilManager(model_router=model_router)
    
    # Mock a council with multiple members
    manager._councils["test_council"] = CouncilConfig(
        name="test_council",
        description="test",
        members=[
            CouncilMemberConfig(member_id="m1", router_mode="m", router_task_type="t", weight=1.0),
            CouncilMemberConfig(member_id="m2", router_mode="m", router_task_type="t", weight=1.0)
        ],
        decision_mode="arbiter_llm"
    )
    
    manager._ask_member = MagicMock(return_value='{"status": "ok"}')
    
    # Low importance should trigger fast track
    q = CouncilQuestion(topic="test", importance="low", prompt="test")
    res = manager.run_council("test_council", q)
    
    # Verify only one member was asked
    assert manager._ask_member.call_count == 1
    assert len(res.member_replies) == 1

def test_council_fast_path_simple_complexity():
    model_router = MagicMock()
    model_router.route.return_value = MagicMock(provider="ollama", name="test")
    
    manager = CouncilManager(model_router=model_router)
    manager._councils["test_council"] = CouncilConfig(
        name="test_council",
        description="test",
        members=[
            CouncilMemberConfig(member_id="m1", router_mode="m", router_task_type="t", weight=1.0),
            CouncilMemberConfig(member_id="m2", router_mode="m", router_task_type="t", weight=1.0)
        ],
        decision_mode="arbiter_llm"
    )
    manager._ask_member = MagicMock(return_value='{"status": "ok"}')
    
    # Normal importance but simple complexity should trigger fast track
    q = CouncilQuestion(topic="test", importance="normal", prompt="Hello")
    res = manager.run_council("test_council", q)
    
    assert manager._ask_member.call_count == 1
    assert len(res.member_replies) == 1


def test_done_council_local_fast_path_disabled_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH", "1")
    monkeypatch.setenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH_COUNCILS", "planner,done,pre_sensing")
    monkeypatch.delenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH_DONE", raising=False)

    manager = CouncilManager(model_router=MagicMock())
    q = CouncilQuestion(topic="done_check", importance="normal", prompt="done?")
    assert manager._should_force_local_fast_path(council_name="done", question=q, complexity="simple") is False
