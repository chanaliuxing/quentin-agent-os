from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


DEFAULT_FAILURE_ROUTER_POLICY: dict[str, Any] = {
    "structural_codes_force_replan": [
        "PATH_CONFLICT",
        "MISSING_TEST_BINDING",
        "CONTRACT_MISMATCH",
    ],
    "max_repeat_before_replan": 2,
    "non_retryable_failure_types": [
        "RUNNER_USAGE_LIMIT",
        "MISSING_DEV_ARTIFACT",
        "MISSING_QA_ARTIFACT",
        "MISSING_DEV_RESULT",
        "MISSING_QA_RESULT",
        "MISSING_REVIEWER_RESULT",
        "MISSING_REQUIRED_TEST",
        "REQUIRED_TEST_FAILED",
        "GRADER_FAILED",
        "BUSINESS_REJECTION_UNMAPPED",
        "BUSINESS_EVIDENCE_MISSING",
        "BUSINESS_TEST_POLICY_GAP",
        "BUSINESS_GRADER_CONTRACT_GAP",
        "AGENT_SUBPROCESS_NONZERO_EXIT",
        "AGENT_OUTPUT_MISSING",
        "AGENT_CONTRACT_VIOLATION",
        "AGENT_ARTIFACT_WRITE_FAILED",
        "AGENT_RUNNER_SESSION_DEGRADED",
        "AGENT_RESULT_PARSE_FAILED",
    ],
    "failure_type_actions": {
        "RUNNER_USAGE_LIMIT": {"action": "replan_from_spec", "owner": "integrator"},
        "MISSING_DEV_ARTIFACT": {"action": "replan_from_spec", "owner": "dev"},
        "MISSING_QA_ARTIFACT": {"action": "replan_from_spec", "owner": "qa"},
        "MISSING_DEV_RESULT": {"action": "replan_from_spec", "owner": "dev"},
        "MISSING_QA_RESULT": {"action": "replan_from_spec", "owner": "qa"},
        "MISSING_REVIEWER_RESULT": {"action": "replan_from_spec", "owner": "reviewer"},
        "MISSING_PLANNER_RESULT": {"action": "retry_same_plan", "owner": "planner"},
        "PLANNER_HANDOFF_STATE_MISMATCH": {"action": "retry_same_plan", "owner": "planner"},
        "MISSING_REQUIRED_TEST": {"action": "replan_from_spec", "owner": "qa"},
        "REQUIRED_TEST_FAILED": {"action": "replan_from_spec", "owner": "qa"},
        "GRADER_FAILED": {"action": "replan_from_spec", "owner": "integrator"},
        "BUSINESS_REJECTION_UNMAPPED": {"action": "taxonomy_review_required", "owner": "integrator"},
        "BUSINESS_EVIDENCE_MISSING": {"action": "taxonomy_review_required", "owner": "integrator"},
        "BUSINESS_TEST_POLICY_GAP": {"action": "replan_from_spec", "owner": "qa"},
        "BUSINESS_GRADER_CONTRACT_GAP": {"action": "replan_from_spec", "owner": "integrator"},
        "AGENT_SUBPROCESS_NONZERO_EXIT": {"action": "replan_from_spec", "owner": "dev"},
        "AGENT_OUTPUT_MISSING": {"action": "replan_from_spec", "owner": "dev"},
        "AGENT_CONTRACT_VIOLATION": {"action": "replan_from_spec", "owner": "reviewer"},
        "AGENT_ARTIFACT_WRITE_FAILED": {"action": "replan_from_spec", "owner": "dev"},
        "AGENT_RUNNER_SESSION_DEGRADED": {"action": "replan_from_spec", "owner": "integrator"},
        "AGENT_RESULT_PARSE_FAILED": {"action": "replan_from_spec", "owner": "reviewer"},
    },
    "failure_type_stage_actions": {
        "AGENT_SUBPROCESS_NONZERO_EXIT": {
            "planner": {"action": "retry_same_plan", "owner": "planner"},
            "reviewer": {"action": "retry_same_plan", "owner": "reviewer"},
            "dev": {"action": "replan_from_spec", "owner": "dev"},
            "qa": {"action": "replan_from_spec", "owner": "qa"},
        }
    },
    "stage_actions": {
        "required_test_missing": {"action": "replan_from_spec", "owner": "qa"},
        "grader_failed": {"action": "replan_from_spec", "owner": "integrator"},
        "review_gate_rejected": {"action": "replan_from_spec", "owner": "reviewer"},
        "dev_output_missing": {"action": "retry_same_plan", "owner": "dev"},
        "reviewer_output_missing": {"action": "retry_same_plan", "owner": "reviewer"},
        "qa_output_missing": {"action": "retry_same_plan", "owner": "qa"},
        "dev_contract_failed": {"action": "retry_same_plan", "owner": "dev"},
        "qa_contract_failed": {"action": "retry_same_plan", "owner": "qa"},
        "module_pipeline_failed": {"action": "retry_same_plan", "owner": "integrator"},
    },
}

RECOVERY_EXPECTED_TERMINAL_STATE: dict[tuple[str, str], str] = {
    ("MISSING_PLANNER_RESULT", "retry_same_plan"): "REJECTED",
    ("PLANNER_HANDOFF_STATE_MISMATCH", "retry_same_plan"): "REJECTED",
    ("MISSING_REQUIRED_TEST", "replan_from_spec"): "REJECTED",
    ("REQUIRED_TEST_FAILED", "replan_from_spec"): "REJECTED",
    ("GRADER_FAILED", "replan_from_spec"): "REJECTED",
    ("BUSINESS_REJECTION_UNMAPPED", "taxonomy_review_required"): "REJECTED",
    ("BUSINESS_EVIDENCE_MISSING", "taxonomy_review_required"): "REJECTED",
    ("AGENT_SUBPROCESS_NONZERO_EXIT", "replan_from_spec"): "REJECTED",
    ("AGENT_OUTPUT_MISSING", "replan_from_spec"): "REJECTED",
    ("AGENT_CONTRACT_VIOLATION", "replan_from_spec"): "REJECTED",
    ("AGENT_ARTIFACT_WRITE_FAILED", "replan_from_spec"): "REJECTED",
    ("AGENT_RUNNER_SESSION_DEGRADED", "replan_from_spec"): "REJECTED",
    ("AGENT_RESULT_PARSE_FAILED", "replan_from_spec"): "REJECTED",
}


def load_failure_router_policy(policy_file: Path | None = None) -> dict[str, Any]:
    path = policy_file or (settings.project_root / "policies" / "failure_router_policy.json")
    if not path.exists():
        return dict(DEFAULT_FAILURE_ROUTER_POLICY)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_FAILURE_ROUTER_POLICY)
    merged = dict(DEFAULT_FAILURE_ROUTER_POLICY)
    for key, value in payload.items():
        if key == "failure_type_actions" and isinstance(value, dict):
            failure_type_actions = dict(merged.get("failure_type_actions", {}))
            for failure_key, failure_value in value.items():
                if isinstance(failure_value, dict):
                    failure_type_actions[str(failure_key)] = dict(failure_value)
            merged["failure_type_actions"] = failure_type_actions
            continue
        if key == "stage_actions" and isinstance(value, dict):
            stage_actions = dict(merged.get("stage_actions", {}))
            for stage_key, stage_value in value.items():
                if isinstance(stage_value, dict):
                    stage_actions[str(stage_key)] = dict(stage_value)
            merged["stage_actions"] = stage_actions
            continue
        if key == "failure_type_stage_actions" and isinstance(value, dict):
            stage_overrides = dict(merged.get("failure_type_stage_actions", {}))
            for failure_key, by_stage in value.items():
                if not isinstance(by_stage, dict):
                    continue
                current = dict(stage_overrides.get(str(failure_key), {}) or {})
                for stage_key, stage_value in by_stage.items():
                    if isinstance(stage_value, dict):
                        current[str(stage_key)] = dict(stage_value)
                stage_overrides[str(failure_key)] = current
            merged["failure_type_stage_actions"] = stage_overrides
            continue
        merged[key] = value
    return merged


def route_recovery_action(
    *,
    status: str,
    acceptance_status: str,
    failed_modules: list[str],
    replan_rounds: int,
    reviewer_codes: list[str] | None = None,
    failure_type: str = "",
    first_failure_stage: str = "",
    failure_signature_count: int = 0,
    max_review_loops: int = 2,
    policy: dict[str, Any] | None = None,
) -> str:
    if status == "completed" and acceptance_status == "passed":
        return "advance"

    policy_payload = policy or load_failure_router_policy()
    reviewer_codes = reviewer_codes or []
    structural_code_set = {
        str(item).strip()
        for item in list(policy_payload.get("structural_codes_force_replan", []) or [])
        if str(item).strip()
    }
    if any(code in structural_code_set for code in reviewer_codes):
        return "replan_from_spec"

    failure_type_text = failure_type.strip()
    failure_type_actions = dict(policy_payload.get("failure_type_actions", {}) or {})
    stage = first_failure_stage.strip()
    stage_lower = stage.lower()
    if stage_lower.endswith("_handoff_failed"):
        stage_lower = stage_lower.replace("_handoff_failed", "")
    if stage_lower.endswith("_contract_failed"):
        stage_lower = stage_lower.replace("_contract_failed", "")
    if stage_lower.endswith("_output_missing"):
        stage_lower = stage_lower.replace("_output_missing", "")

    stage_overrides = dict(policy_payload.get("failure_type_stage_actions", {}) or {})
    failure_stage_overrides = dict(stage_overrides.get(failure_type_text, {}) or {})
    stage_override_payload = dict(failure_stage_overrides.get(stage_lower, {}) or {})
    stage_action = str(stage_override_payload.get("action", "")).strip()
    stage_action_from_override = bool(stage_action)

    failure_type_payload = dict(failure_type_actions.get(failure_type_text, {}) or {})
    if not stage_action:
        stage_action = str(failure_type_payload.get("action", "")).strip()

    if not stage_action:
        stage_actions = dict(policy_payload.get("stage_actions", {}) or {})
        stage_payload = dict(stage_actions.get(stage, {}) or {})
        stage_action = str(stage_payload.get("action", "")).strip()
    if not stage_action:
        stage_action = "retry_same_plan" if failed_modules else "replan_from_spec"

    non_retryable_failure_types = {
        str(item).strip()
        for item in list(policy_payload.get("non_retryable_failure_types", []) or [])
        if str(item).strip()
    }
    if (
        stage_action == "retry_same_plan"
        and failure_type_text in non_retryable_failure_types
        and not stage_action_from_override
    ):
        return "replan_from_spec"

    if stage_action == "retry_same_plan" and replan_rounds >= max_review_loops:
        return "replan_from_spec"

    repeat_limit = int(policy_payload.get("max_repeat_before_replan", 2))
    if stage_action == "retry_same_plan" and failure_signature_count >= max(1, repeat_limit):
        return "replan_from_spec"

    if acceptance_status != "rejected":
        return "escalate_to_human"
    return stage_action


def expected_terminal_state_for_recovery(*, failure_type: str, recovery_action: str) -> str:
    code = str(failure_type).strip().upper()
    action = str(recovery_action).strip()
    return RECOVERY_EXPECTED_TERMINAL_STATE.get((code, action), "")
