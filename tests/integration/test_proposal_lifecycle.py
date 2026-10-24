import pytest
from quentin.evolution.proposal_engine import ProposalEngine
from quentin.evolution.proposal_gate import ProposalGate
from quentin.evolution.proposal_orchestrator import ProposalOrchestrator

def test_proposal_lifecycle_success():
    engine = ProposalEngine()
    gate = ProposalGate()
    orchestrator = ProposalOrchestrator(engine, gate)

    # Mock metrics that should trigger a proposal
    metrics = {"avg_latency_ms": 6000}
    
    results = orchestrator.run_cycle(metrics=metrics)
    
    assert len(results) > 0
    proposal = results[0]
    assert proposal.status == "applied"
    assert "routing_policy" in proposal.target
    assert proposal.proposed_changes["preference"] == "speed"

def test_proposal_lifecycle_gate_reject():
    engine = ProposalEngine()
    gate = ProposalGate()
    orchestrator = ProposalOrchestrator(engine, gate)

    # High risk proposal should be rejected by our mock gate
    gaps = ["memory_bottleneck"] # triggers medium risk, but let's force a high risk if we can
    
    # Actually, let's just test the gate rejection for a high risk manually created proposal
    from quentin.evolution.proposal_engine import Proposal
    high_risk_proposal = Proposal(
        target="core_system",
        risk_level="high",
        proposed_changes={"delete": "all"},
        rollback_plan="N/A"
    )
    
    # We can't easily inject this into the cycle without mocking the engine, 
    # but we can test the gate directly.
    eval_res = gate.evaluate(high_risk_proposal)
    assert not eval_res.passed
    assert "High risk" in eval_res.reason

def test_proposal_lifecycle_protected_path():
    gate = ProposalGate()
    from quentin.evolution.proposal_engine import Proposal
    
    protected_proposal = Proposal(
        target="governance.yaml",
        risk_level="low",
        proposed_changes={"some": "change"},
        rollback_plan="revert"
    )
    
    eval_res = gate.evaluate(protected_proposal)
    assert not eval_res.passed
    assert "protected path" in eval_res.reason
