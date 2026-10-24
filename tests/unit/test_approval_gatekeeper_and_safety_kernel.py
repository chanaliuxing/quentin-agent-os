from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from quentin.infra.security.approval import approval_gate
from quentin.kernel.policy import ActionRequest, PolicyDecision
from quentin.kernel.safety import SafetyKernel
from quentin.kernel.budget import BudgetDecision


class _AllowAllPolicy:
    def evaluate(self, action: ActionRequest) -> PolicyDecision:  # noqa: ARG002
        return PolicyDecision(allow=True, reason="ok", modifications={})


class _AllowAllBudget:
    def resolve_profile(self, *, environment: str, domain: str) -> str:  # noqa: ARG002
        return "default"

    def check_and_reserve(self, *, profile_id: str, tokens: int, usd: float) -> BudgetDecision:  # noqa: ARG002
        return BudgetDecision(
            allow=True,
            reason="ok",
            remaining_tokens_today=10**9,
            remaining_tokens_month=10**9,
            remaining_usd_today=1e9,
            remaining_usd_month=1e9,
        )


def test_approval_gatekeeper_sync_can_be_resolved(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_APPROVAL_TIMEOUT_SEC", "2")

    # Use a short timeout for this test.
    old_timeout = approval_gate.timeout_seconds
    approval_gate.timeout_seconds = 2

    out: dict = {}

    def _waiter() -> None:
        approved, req_id = approval_gate.request_approval_sync(
            tool_name="shell.run_command",
            args={"command": "echo hi"},
            reason="unit_test",
        )
        out["approved"] = approved
        out["request_id"] = req_id

    t = threading.Thread(target=_waiter, daemon=True)
    t.start()

    # Wait until request appears
    req_id = None
    deadline = time.time() + 2.0
    while time.time() < deadline:
        pending = approval_gate.list_pending()
        if pending:
            req_id = pending[0]["request_id"]
            break
        time.sleep(0.01)
    assert req_id, "approval request should be pending"

    approval_gate.resolve_request(req_id, True)
    t.join(timeout=2.0)

    assert out.get("approved") is True

    approval_gate.timeout_seconds = old_timeout


def test_safety_kernel_requires_approval_when_requested(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUENTIN_APPROVAL_GATE", "1")
    monkeypatch.setenv("QUENTIN_APPROVAL_TIMEOUT_SEC", "2")

    kernel = SafetyKernel(
        repo_root=tmp_path,
        policy_engine=_AllowAllPolicy(),
        budget_controller=_AllowAllBudget(),
    )

    out: dict = {}

    def _guard() -> None:
        action = ActionRequest.new(
            actor="unit_test",
            action_type="tool_call",
            domain="core",
            environment="sandbox",
            risk_level="medium",
            description="tool_call:shell.run_command",
            metadata={
                "tool_name": "shell.run_command",
                "approval_required": True,
                "approval_reason": "unit_test_approval",
                "approval_context": {"command": "echo hi"},
            },
        )
        out["guard"] = kernel.guard_action(action)

    t = threading.Thread(target=_guard, daemon=True)
    t.start()

    req_id = None
    deadline = time.time() + 2.0
    while time.time() < deadline:
        pending = approval_gate.list_pending()
        if pending:
            req_id = pending[0]["request_id"]
            break
        time.sleep(0.01)
    assert req_id, "approval request should be pending"

    approval_gate.resolve_request(req_id, True)
    t.join(timeout=2.0)

    guard = out.get("guard")
    assert guard is not None
    assert bool(getattr(guard, "allow", False)) is True

