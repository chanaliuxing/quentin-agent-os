from __future__ import annotations

from typing import Any


DEFAULT_REPAIR_TEMPLATES = {
    "dev_output_missing": "Dev agent must produce valid JSON contract result file before exit.",
    "reviewer_output_missing": "Reviewer agent must output strict JSON with verdict, findings, and finding_codes.",
    "required_test_missing": "Ensure required_tests are explicitly mapped to executed gates and pass.",
    "required_test_failed": "Required test gates ran but failed; inspect scoped test failures and align gate coverage to the module under change.",
    "review_gate_rejected:PATH_CONFLICT": "Fix path policy conflicts and constrain outputs to allowed paths.",
    "review_gate_rejected:MISSING_TEST_BINDING": "Add test-binding details from AcceptanceSpec into planner and QA tasks.",
    "grader_failed:contract_validator": "Inspect grader_details for contract_validator, repair the failing contract or status violation, then rerun acceptance.",
}


def resolve_repair_template(
    *,
    failure_signature: str,
    first_failure_stage: str,
    policy_templates: dict[str, str] | None = None,
) -> str:
    templates = dict(DEFAULT_REPAIR_TEMPLATES)
    if policy_templates:
        templates.update({str(k): str(v) for k, v in policy_templates.items()})

    signature = failure_signature.strip()
    stage = first_failure_stage.strip()
    if signature and signature in templates:
        return templates[signature]

    if signature and ":" in signature:
        prefix_parts = signature.split(":")
        for size in range(len(prefix_parts) - 1, 0, -1):
            candidate = ":".join(prefix_parts[:size])
            if candidate in templates:
                return templates[candidate]

    if stage and stage in templates:
        return templates[stage]

    return "No explicit repair template matched; refine spec, tests, and output contracts for failed stage."


def policy_structural_codes(policy: dict[str, Any]) -> set[str]:
    values = policy.get("structural_finding_codes", [])
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}
