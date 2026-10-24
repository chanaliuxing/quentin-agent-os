# tests/integration/test_canary_mode.py

import pytest
import os
import json
from pathlib import Path
from quentin.kernel.policy import PolicyEngine, ActionRequest
from quentin.kernel.budget import BudgetController

def test_canary_policy_enforcement():
    os.environ["QUENTIN_CANARY"] = "1"
    engine = PolicyEngine()
    
    # High risk should be denied in canary
    action = ActionRequest.new(
        actor="test",
        action_type="code_patch",
        risk_level="high",
        environment="sandbox"
    )
    decision = engine.evaluate(action)
    assert decision.allow is False
    assert "Canary mode active" in decision.reason
    
    # Medium risk code_patch should allow but forbid auto-apply
    action_med = ActionRequest.new(
        actor="test",
        action_type="code_patch",
        risk_level="medium",
        environment="sandbox"
    )
    dec_med = engine.evaluate(action_med)
    assert dec_med.allow is True
    assert dec_med.modifications.get("allow_auto_apply") is False

def test_canary_budget_enforcement(tmp_path):
    os.environ["QUENTIN_CANARY"] = "1"
    # Use tmp_path for budget state to avoid polluting real data
    state_path = tmp_path / "budget_state.json"
    bc = BudgetController(state_path=state_path)
    
    # Large request should be denied by canary budget (limit 50k)
    dec = bc.check_and_reserve(profile_id="default", tokens=100_000, usd=0.0)
    assert dec.allow is False
    assert "Budget exceeded" in dec.reason
    
    # Small request should be allowed
    dec_small = bc.check_and_reserve(profile_id="default", tokens=1000, usd=0.0)
    assert dec_small.allow is True
