from app.review.governance_review import evaluate_governance_review


def test_governance_review_rejects_hard_risk(monkeypatch):
    monkeypatch.setattr(
        "app.review.governance_review.evaluate_auto_review",
        lambda phase_id="", hooks_dir=None: {
            "decision": "rejected",
            "confidence": 0.8,
            "notes": "risk",
            "risk_signals": ["FAILED_GRADERS:contract_validator"],
            "hook": {"phase_id": "phase_01"},
        },
    )
    result = evaluate_governance_review(phase_id="phase_01")
    assert result["decision"] == "rejected"


def test_governance_review_soft_approves_metadata_only_risks(monkeypatch):
    monkeypatch.setattr(
        "app.review.governance_review.evaluate_auto_review",
        lambda phase_id="", hooks_dir=None: {
            "decision": "rejected",
            "confidence": 0.4,
            "notes": "soft",
            "risk_signals": ["FIRST_FAILURE_STAGE:grader_failed", "OWNER_AGENT:integrator"],
            "hook": {"phase_id": "phase_01"},
        },
    )
    result = evaluate_governance_review(phase_id="phase_01")
    assert result["decision"] == "approved"
    assert result["confidence"] >= 0.65
