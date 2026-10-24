from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import settings


DEFAULT_RECOVERY_ROLLOUT_POLICY: dict[str, Any] = {
    "mode": "shadow",
    "canary_percentage": 10,
    "actions": {
        "replan_from_spec": {
            "eligibility_rule": "acceptance_status=rejected",
            "max_retry_budget": 2,
            "expected_terminal_state": "REJECTED",
            "rollback_rule": "disable_action_on_terminal_mismatch",
        },
        "taxonomy_review_required": {
            "eligibility_rule": "primary_failure_type in BUSINESS_*",
            "max_retry_budget": 1,
            "expected_terminal_state": "REJECTED",
            "rollback_rule": "disable_action_on_repeat_window",
        },
    },
}


def load_recovery_rollout_policy(policy_file: Path | None = None) -> dict[str, Any]:
    path = policy_file or (settings.project_root / "policies" / "recovery_rollout_policy.json")
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_RECOVERY_ROLLOUT_POLICY))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_RECOVERY_ROLLOUT_POLICY))
    merged = json.loads(json.dumps(DEFAULT_RECOVERY_ROLLOUT_POLICY))
    merged.update({k: v for k, v in payload.items() if k != "actions"})
    actions = dict(merged.get("actions", {}))
    for key, value in dict(payload.get("actions", {}) or {}).items():
        if isinstance(value, dict):
            action_payload = dict(actions.get(str(key), {}))
            action_payload.update(value)
            actions[str(key)] = action_payload
    merged["actions"] = actions
    safe_mode = str(settings.recovery_safe_mode).strip().lower()
    if safe_mode in {"shadow", "canary", "full"}:
        merged["mode"] = safe_mode
    return merged


def evaluate_recovery_rollout(
    *,
    policy: dict[str, Any],
    project_id: str,
    phase_id: str,
    action: str,
    primary_failure_type: str,
    acceptance_status: str,
    retry_count: int,
) -> dict[str, Any]:
    mode = str(policy.get("mode", "shadow")).strip().lower()
    action_cfg = dict(dict(policy.get("actions", {}) or {}).get(action, {}) or {})
    max_retry_budget = int(action_cfg.get("max_retry_budget", 0))
    eligible = _is_eligible(
        action=action,
        primary_failure_type=primary_failure_type,
        acceptance_status=acceptance_status,
    )
    if retry_count >= max_retry_budget > 0:
        return {"execute": False, "mode": mode, "reason": "retry_budget_exceeded", "shadow": mode == "shadow"}
    if not eligible:
        return {"execute": False, "mode": mode, "reason": "not_eligible", "shadow": mode == "shadow"}
    if mode == "shadow":
        return {"execute": False, "mode": mode, "reason": "shadow_mode", "shadow": True}
    if mode == "full":
        return {"execute": True, "mode": mode, "reason": "full_mode", "shadow": False}
    if mode == "canary":
        percentage = int(policy.get("canary_percentage", 0))
        token = f"{project_id}:{phase_id}:{action}:{primary_failure_type}"
        bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % 100
        execute = bucket < max(0, min(100, percentage))
        return {
            "execute": execute,
            "mode": mode,
            "reason": "canary_selected" if execute else "canary_skipped",
            "shadow": False,
            "bucket": bucket,
            "canary_percentage": percentage,
        }
    return {"execute": False, "mode": mode, "reason": "unknown_mode", "shadow": True}


def _is_eligible(*, action: str, primary_failure_type: str, acceptance_status: str) -> bool:
    if str(acceptance_status).strip().lower() != "rejected":
        return False
    if action == "taxonomy_review_required":
        return str(primary_failure_type).strip().upper().startswith("BUSINESS_")
    return action in {"replan_from_spec", "taxonomy_review_required"}
