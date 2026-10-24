from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings

from .auto_review import evaluate_auto_review


DEFAULT_GOVERNANCE_REVIEW_POLICY: dict[str, Any] = {
    "force_reject_signal_prefixes": [
        "MISSING_REQUIRED_TESTS",
        "FAILED_GRADERS",
        "STRUCTURAL_CODES",
        "EVIDENCE_MISSING",
    ],
    "soft_approve_signal_prefixes": [
        "FIRST_FAILURE_STAGE",
        "OWNER_AGENT",
    ],
    "soft_approve_max_signal_count": 2,
    "min_confidence": 0.65,
}


def load_governance_review_policy(policy_file: Path | None = None) -> dict[str, Any]:
    path = policy_file or (settings.project_root / "policies" / "governance_review_policy.json")
    if not path.exists():
        return dict(DEFAULT_GOVERNANCE_REVIEW_POLICY)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_GOVERNANCE_REVIEW_POLICY)
    policy = dict(DEFAULT_GOVERNANCE_REVIEW_POLICY)
    for key, value in payload.items():
        policy[key] = value
    return policy


def evaluate_governance_review(
    *,
    phase_id: str = "",
    hooks_dir: Path | None = None,
    policy_file: Path | None = None,
) -> dict[str, Any]:
    auto_eval = evaluate_auto_review(phase_id=phase_id, hooks_dir=hooks_dir)
    hook = auto_eval.get("hook") or {}
    if not hook:
        return {
            "decision": "rejected",
            "confidence": 0.0,
            "notes": "No pending hook for governance review.",
            "policy_version": "governance_review_policy_v1",
            "risk_signals": ["NO_HOOK"],
            "hook": None,
        }

    decision = str(auto_eval.get("decision", "rejected")).strip().lower()
    confidence = float(auto_eval.get("confidence", 0.0))
    risk_signals = [str(item) for item in auto_eval.get("risk_signals", [])]
    policy = load_governance_review_policy(policy_file=policy_file)

    force_reject_prefixes = tuple(
        str(item).strip()
        for item in list(policy.get("force_reject_signal_prefixes", []) or [])
        if str(item).strip()
    )
    if any(signal.startswith(force_reject_prefixes) for signal in risk_signals):
        return {
            "decision": "rejected",
            "confidence": max(confidence, 0.8),
            "notes": "Governance rejected due to hard risk signals.",
            "policy_version": "governance_review_policy_v1",
            "risk_signals": risk_signals,
            "hook": hook,
        }

    soft_prefixes = tuple(
        str(item).strip()
        for item in list(policy.get("soft_approve_signal_prefixes", []) or [])
        if str(item).strip()
    )
    soft_max = int(policy.get("soft_approve_max_signal_count", 2))
    all_soft = bool(risk_signals) and all(signal.startswith(soft_prefixes) for signal in risk_signals)
    if decision == "approved" and confidence >= float(policy.get("min_confidence", 0.65)):
        return {
            "decision": "approved",
            "confidence": confidence,
            "notes": "Governance accepted auto-review approved result.",
            "policy_version": "governance_review_policy_v1",
            "risk_signals": risk_signals,
            "hook": hook,
        }
    if all_soft and len(risk_signals) <= soft_max:
        return {
            "decision": "approved",
            "confidence": max(confidence, float(policy.get("min_confidence", 0.65))),
            "notes": "Governance soft-approved metadata-only risks.",
            "policy_version": "governance_review_policy_v1",
            "risk_signals": risk_signals,
            "hook": hook,
        }
    return {
        "decision": "rejected",
        "confidence": max(confidence, 0.75),
        "notes": "Governance rejected due to unresolved non-soft risks.",
        "policy_version": "governance_review_policy_v1",
        "risk_signals": risk_signals,
        "hook": hook,
    }

