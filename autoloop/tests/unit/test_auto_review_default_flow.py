import pytest

from app.config import settings
from app.main import _maybe_auto_review_resume


@pytest.mark.asyncio
async def test_default_auto_review_resumes_when_approved(monkeypatch):
    monkeypatch.setattr(settings, "auto_review_enabled", True)
    monkeypatch.setattr(settings, "auto_review_min_confidence", 0.8)
    monkeypatch.setattr(settings, "auto_review_max_auto_resumes", 1)
    monkeypatch.setattr(settings, "temporal_mock_mode", True)

    monkeypatch.setattr(
        "app.main.evaluate_auto_review",
        lambda phase_id="": {
            "decision": "approved",
            "confidence": 0.95,
            "notes": "ok",
            "risk_signals": [],
        },
    )

    called = {"resolved": False, "resumed": False}

    def _fake_resolve_human_review(**kwargs):
        called["resolved"] = True
        return {"resolution_file": "/tmp/resolution.json"}

    class _FakeWorker:
        async def run_workflow(self, project_id, prd_path):
            called["resumed"] = True
            return {"status": "failed", "acceptance_status": "rejected"}

    monkeypatch.setattr("app.main.resolve_human_review", _fake_resolve_human_review)
    monkeypatch.setattr("app.main.MockTemporalWorker", _FakeWorker)

    await _maybe_auto_review_resume(
        project_id="p1",
        prd_path="/tmp/prd.md",
        result={"phase_id": "phase_01", "human_review_hook": "/tmp/hook.json"},
        auto_resume_depth=0,
    )

    assert called["resolved"] is True
    assert called["resumed"] is True


@pytest.mark.asyncio
async def test_default_auto_review_skips_resume_on_reject(monkeypatch):
    monkeypatch.setattr(settings, "auto_review_enabled", True)
    monkeypatch.setattr(settings, "auto_review_min_confidence", 0.8)
    monkeypatch.setattr(settings, "auto_review_max_auto_resumes", 1)
    monkeypatch.setattr(settings, "governance_review_enabled", True)
    monkeypatch.setattr(settings, "governance_review_auto_resume", False)

    monkeypatch.setattr(
        "app.main.evaluate_auto_review",
        lambda phase_id="": {
            "decision": "rejected",
            "confidence": 0.9,
            "notes": "risk",
            "risk_signals": ["FAILED_GRADERS:contract_validator"],
        },
    )

    monkeypatch.setattr(
        "app.main.evaluate_governance_review",
        lambda phase_id="": {
            "decision": "rejected",
            "confidence": 0.88,
            "notes": "governance reject",
            "risk_signals": ["FAILED_GRADERS:contract_validator"],
            "policy_version": "governance_review_policy_v1",
            "hook": {"phase_id": "phase_01"},
        },
    )

    called = {"resolved": False}

    def _fake_resolve_human_review(**kwargs):
        called["resolved"] = True
        return {"resolution_file": "/tmp/resolution.json"}

    monkeypatch.setattr("app.main.resolve_human_review", _fake_resolve_human_review)

    await _maybe_auto_review_resume(
        project_id="p1",
        prd_path="/tmp/prd.md",
        result={"phase_id": "phase_01", "human_review_hook": "/tmp/hook.json"},
        auto_resume_depth=0,
    )

    assert called["resolved"] is True
