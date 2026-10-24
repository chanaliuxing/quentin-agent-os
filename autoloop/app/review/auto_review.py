from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import AgentRole, extract_json_payload
from app.utils import get_result_file

from .human_review import latest_human_review
from .repair_templates import policy_structural_codes, resolve_repair_template


DEFAULT_AUTO_REVIEW_POLICY = {
    "profiles": {
        "normal": {
            "auto_approve_conditions": {
                "hook_acceptance_status": "passed",
                "evidence_acceptance_status": "passed",
                "test_status": "success",
                "require_no_missing_tests": True,
                "require_all_graders_pass": True,
            },
            "confidence": {"approve": 0.9, "reject": 0.8},
        },
        "strict": {
            "auto_approve_conditions": {
                "hook_acceptance_status": "passed",
                "evidence_acceptance_status": "passed",
                "test_status": "success",
                "require_no_missing_tests": True,
                "require_all_graders_pass": True,
            },
            "confidence": {"approve": 0.95, "reject": 0.85},
        },
    },
    "structural_finding_codes": ["PATH_CONFLICT", "MISSING_TEST_BINDING", "CONTRACT_MISMATCH"],
    "hard_reject_signal_prefixes": [
        "MISSING_REQUIRED_TESTS",
        "FAILED_GRADERS",
        "STRUCTURAL_CODES",
        "EVIDENCE_MISSING",
    ],
    "repair_templates": {},
}


def evaluate_auto_review(
    *,
    phase_id: str = "",
    hooks_dir: Path | None = None,
) -> dict[str, Any]:
    hook = _resolve_hook(phase_id=phase_id, hooks_dir=hooks_dir)
    policy = load_auto_review_policy()
    if not hook:
        return {
            "decision": "rejected",
            "confidence": 0.0,
            "notes": "No pending human-review hook found.",
            "risk_signals": ["NO_HOOK"],
            "hook": None,
        }

    evidence_payload = _load_evidence_payload(str(hook.get("evidence_file", "")))
    risk_signals: list[str] = []

    if not evidence_payload:
        risk_signals.append("EVIDENCE_MISSING")
    else:
        missing_required_tests = list(evidence_payload.get("missing_required_tests", []) or [])
        failed_graders = sorted(
            key
            for key, value in dict(evidence_payload.get("grader_results", {}) or {}).items()
            if str(value) != "pass"
        )
        if missing_required_tests:
            risk_signals.append(f"MISSING_REQUIRED_TESTS:{','.join(sorted(str(x) for x in missing_required_tests))}")
        if failed_graders:
            risk_signals.append(f"FAILED_GRADERS:{','.join(failed_graders)}")
        first_failure_stage = str(evidence_payload.get("first_failure_stage", "")).strip()
        if first_failure_stage:
            risk_signals.append(f"FIRST_FAILURE_STAGE:{first_failure_stage}")
        owner_agent = str(evidence_payload.get("owner_agent", "")).strip()
        if owner_agent:
            risk_signals.append(f"OWNER_AGENT:{owner_agent}")

    finding_codes = _collect_reviewer_finding_codes(
        phase_id=str(hook.get("phase_id", "")).strip(),
        failed_modules=[str(item) for item in hook.get("failed_modules", []) or []],
    )
    structural_code_set = policy_structural_codes(policy)
    structural_codes = sorted(code for code in finding_codes if code in structural_code_set)
    if structural_codes:
        risk_signals.append(f"STRUCTURAL_CODES:{','.join(structural_codes)}")

    profile_name = str(policy.get("active_profile", settings.auto_review_profile)).strip() or "normal"
    profile_payload = _resolve_policy_profile(policy=policy, profile_name=profile_name)
    accepted = _can_auto_approve(
        hook=hook,
        evidence_payload=evidence_payload,
        structural_codes=structural_codes,
        profile_payload=profile_payload,
    )
    repair_template = resolve_repair_template(
        failure_signature=str(evidence_payload.get("failure_signature", "")).strip(),
        first_failure_stage=str(evidence_payload.get("first_failure_stage", "")).strip(),
        policy_templates=dict(policy.get("repair_templates", {}) or {}),
    )
    if accepted:
        confidence = float(profile_payload.get("confidence", {}).get("approve", 0.9))
        notes = "Auto-approved: acceptance passed and no structural risk signals detected."
        decision = "approved"
    else:
        confidence = float(profile_payload.get("confidence", {}).get("reject", 0.8)) if risk_signals else 0.6
        notes = "Auto-rejected due to risk signals: " + ", ".join(risk_signals or ["UNKNOWN"])
        notes = f"{notes} | Repair template: {repair_template}"
        decision = "rejected"

    return {
        "decision": decision,
        "confidence": confidence,
        "notes": notes,
        "risk_signals": risk_signals,
        "finding_codes": finding_codes,
        "repair_template": repair_template,
        "policy_version": f"auto_review_policy_v1:{profile_name}",
        "hook": hook,
    }


def _can_auto_approve(
    *,
    hook: dict[str, Any],
    evidence_payload: dict[str, Any],
    structural_codes: list[str],
    profile_payload: dict[str, Any],
) -> bool:
    conditions = dict(profile_payload.get("auto_approve_conditions", {}) or {})
    if str(hook.get("acceptance_status", "")).strip() != str(
        conditions.get("hook_acceptance_status", "passed")
    ):
        return False
    if not evidence_payload:
        return False
    if str(evidence_payload.get("acceptance_status", "")).strip() != str(
        conditions.get("evidence_acceptance_status", "passed")
    ):
        return False
    if str(evidence_payload.get("test_status", "")).strip() != str(
        conditions.get("test_status", "success")
    ):
        return False
    if bool(conditions.get("require_no_missing_tests", True)) and list(
        evidence_payload.get("missing_required_tests", []) or []
    ):
        return False
    grader_results = dict(evidence_payload.get("grader_results", {}) or {})
    if bool(conditions.get("require_all_graders_pass", True)) and any(
        str(value) != "pass" for value in grader_results.values()
    ):
        return False
    if structural_codes:
        return False
    return True


def load_auto_review_policy(policy_file: Path | None = None) -> dict[str, Any]:
    path = policy_file or (settings.project_root / "policies" / "auto_review_policy.json")
    if not path.exists():
        return dict(DEFAULT_AUTO_REVIEW_POLICY)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_AUTO_REVIEW_POLICY)
    policy = dict(DEFAULT_AUTO_REVIEW_POLICY)
    for key, value in payload.items():
        policy[key] = value
    env_profile = os.getenv("AUTO_REVIEW_PROFILE", "").strip()
    if env_profile:
        policy["active_profile"] = env_profile
    else:
        policy["active_profile"] = str(
            policy.get("active_profile", settings.auto_review_profile)
        ).strip() or settings.auto_review_profile
    return policy


def _resolve_policy_profile(*, policy: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profiles = dict(policy.get("profiles", {}) or {})
    if profile_name in profiles and isinstance(profiles[profile_name], dict):
        return dict(profiles[profile_name])
    if "normal" in profiles and isinstance(profiles["normal"], dict):
        return dict(profiles["normal"])
    return dict(DEFAULT_AUTO_REVIEW_POLICY["profiles"]["normal"])


def _resolve_hook(*, phase_id: str, hooks_dir: Path | None = None) -> dict[str, Any] | None:
    if phase_id.strip():
        root = hooks_dir or settings.hooks_dir
        hook_path = root / f"{phase_id.strip()}_human_review_required.json"
        if not hook_path.exists():
            return None
        try:
            payload = json.loads(hook_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        payload["hook_file"] = str(hook_path)
        return payload
    return latest_human_review(hooks_dir=hooks_dir)


def _load_evidence_payload(evidence_file: str) -> dict[str, Any]:
    if not evidence_file:
        return {}
    path = Path(evidence_file)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_reviewer_finding_codes(*, phase_id: str, failed_modules: list[str]) -> list[str]:
    if not phase_id:
        return []
    module_names = failed_modules or ["module_main"]
    codes: list[str] = []
    for module_name in module_names:
        result_file = get_result_file(phase_id, AgentRole.REVIEWER, module_name)
        if not result_file.exists():
            continue
        payload_text = result_file.read_text(encoding="utf-8").strip()
        try:
            payload = extract_json_payload(payload_text)
        except Exception:
            continue
        payload_codes = payload.get("finding_codes", [])
        if isinstance(payload_codes, list):
            codes.extend(str(item) for item in payload_codes if str(item).strip())
    return sorted(set(codes))
