import pytest
from quentin.policy.constraint_dsl import ConstraintDSL, ConstraintRule
from quentin.policy.constraint_verifier import ConstraintVerifier

def test_constraint_core_integrity():
    dsl = ConstraintDSL()
    verifier = ConstraintVerifier(dsl)
    
    # Attempt to patch safety kernel should fail
    action_data = {"target": "quentin/kernel/safety.py", "environment": "sandbox"}
    assert verifier.verify_action("code_patch", action_data) is False
    
    # Normal patch should pass
    safe_data = {"target": "quentin/utils/helpers.py", "environment": "sandbox"}
    assert verifier.verify_action("code_patch", safe_data) is True

def test_constraint_legal_boundary():
    dsl = ConstraintDSL()
    verifier = ConstraintVerifier(dsl)
    
    # Tool call in wrong environment for legal rule
    action_data = {"target": "legal_doc_processor", "environment": "sandbox"}
    # Note: Our legal_boundary rule is generic to 'tool_call', 
    # so any tool call not in legal_sandbox should fail if it hits this rule.
    assert verifier.verify_action("tool_call", action_data) is False
    
    # Correct environment
    ok_data = {"target": "legal_doc_processor", "environment": "legal_sandbox"}
    assert verifier.verify_action("tool_call", ok_data) is True
