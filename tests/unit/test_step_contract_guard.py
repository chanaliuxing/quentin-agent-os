import pytest
from quentin.execution.contract import StepContractGuard
from quentin.planning import PlanStep

def test_step_contract_guard_mutation_without_observation():
    guard = StepContractGuard()
    
    # 1. Mutation step
    mutation = PlanStep(step_id="s1", description="write file", kind="tool", name="fs.write_file", args={"path": "test.py"})
    
    # By default, it warns but returns True unless strict
    assert guard.verify_step(mutation) is True

def test_step_contract_guard_strict_violation(monkeypatch):
    monkeypatch.setenv("QUENTIN_STRICT_STEP_CONTRACT", "1")
    guard = StepContractGuard()
    
    mutation = PlanStep(step_id="s1", description="write file", kind="tool", name="fs.write_file", args={"path": "test.py"})
    assert guard.verify_step(mutation) is False

def test_step_contract_guard_pass_flow(monkeypatch):
    monkeypatch.setenv("QUENTIN_STRICT_STEP_CONTRACT", "1")
    guard = StepContractGuard()
    
    # 1. Observe
    obs = PlanStep(step_id="s1", description="read file", kind="tool", name="fs.read_file", args={"path": "test.py"})
    assert guard.verify_step(obs) is True
    
    # 2. Mutate
    mut = PlanStep(step_id="s2", description="write file", kind="tool", name="fs.write_file", args={"path": "test.py"})
    assert guard.verify_step(mut) is True
