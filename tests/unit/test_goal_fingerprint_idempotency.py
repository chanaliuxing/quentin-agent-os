import pytest
from quentin.utils.hash import get_goal_fingerprint, get_file_hash
from quentin.execution.idempotency import IdempotencyGate
from pathlib import Path

def test_goal_fingerprint_stability():
    goal = "Implement a feature"
    ctx = {"domain": "core", "trace_id": "dynamic-123"}
    f1 = get_goal_fingerprint(goal, ctx)
    
    ctx2 = {"domain": "core", "trace_id": "dynamic-456"}
    f2 = get_goal_fingerprint(goal, ctx2)
    
    assert f1 == f2 # dynamic fields should be ignored

def test_idempotency_gate_logic(tmp_path):
    gate = IdempotencyGate(repo_root=str(tmp_path))
    fingerprint = "test-fp"
    
    # 1. New fingerprint
    assert gate.check(fingerprint) is False
    
    # 2. Mark success
    gate.mark_success(fingerprint)
    assert gate.check(fingerprint) is True

def test_idempotency_gate_with_file_hash(tmp_path):
    gate = IdempotencyGate(repo_root=str(tmp_path))
    fingerprint = "test-fp-file"
    target_file = "test.txt"
    full_path = tmp_path / target_file
    
    full_path.write_text("v1")
    
    # Mark success for v1
    gate.mark_success(fingerprint, target_file)
    assert gate.check(fingerprint, target_file) is True
    
    # Change file content
    full_path.write_text("v2")
    assert gate.check(fingerprint, target_file) is False # State changed
