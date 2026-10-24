from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str) -> List[str]:
    raw = str(os.getenv(name, default) or "")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


@dataclass
class PlanningStrategyPatch:
    patch_id: str
    category: str
    directives: List[str] = field(default_factory=list)
    required_prechecks: List[str] = field(default_factory=list)
    avoid_actions: List[str] = field(default_factory=list)
    prompt_patch: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_PATCH_LIBRARY: Dict[str, Dict[str, Any]] = {
    "plan_execution_misalignment": {
        "patch_id": "tool_alignment_enforcement_v1",
        "directives": [
            "Plan-tool alignment failure: reset step decomposition with explicit tool names per step.",
            "Before each action, verify selected tool matches step-intended tool family.",
            "If alignment fails, perform one corrective rewrite before any broad fallback.",
        ],
        "required_prechecks": ["tool_alignment_check", "delta_explanation"],
        "avoid_actions": ["cross_family_tool_substitution_without_alignment"],
    },
    "environment_timeout_error": {
        "patch_id": "timeout_diagnostics_v1",
        "directives": [
            "Environment timeout detected: switch to low-cost diagnostics before any mutation.",
            "Add timeout-safe probes (pwd/ls/id + one targeted file check) and branch strategy if probe fails.",
            "Avoid long-running or repeated identical tool calls.",
        ],
        "required_prechecks": ["env_diagnostics", "timeout_probe"],
        "avoid_actions": ["repeat_identical_heavy_call"],
    },
    "tool_execution_error": {
        "patch_id": "tool_guardrails_v1",
        "directives": [
            "Tool execution failure: validate path, permission and write policy before edits.",
            "If action fails once, do not repeat without a changed precheck signal.",
        ],
        "required_prechecks": ["path_exists_probe", "write_policy_check"],
        "avoid_actions": ["blind_write_retry"],
    },
    "model_syntax_error": {
        "patch_id": "format_repair_v1",
        "directives": [
            "Model syntax/format failure: simplify step granularity and keep output schema strict.",
            "Avoid complex multi-action steps; emit deterministic, verifiable sequence.",
        ],
        "required_prechecks": ["schema_guard"],
        "avoid_actions": ["multi_action_single_step"],
    },
    "logic_path_error": {
        "patch_id": "branch_replan_v1",
        "directives": [
            "Strategy-path failure: introduce at least one alternative branch from prior failed path.",
            "State explicit delta versus previous attempt before risky steps.",
        ],
        "required_prechecks": ["delta_explanation", "branch_probe"],
        "avoid_actions": ["same_strategy_replay"],
    },
    "mixed": {
        "patch_id": "mixed_failure_decomposition_v1",
        "directives": [
            "Mixed failure: separate environment checks from model/logic correction into distinct steps.",
            "Use one probe to disambiguate root cause before mutation.",
        ],
        "required_prechecks": ["env_diagnostics", "branch_probe"],
        "avoid_actions": ["direct_mutation_without_probe"],
    },
    "system_error": {
        "patch_id": "system_recovery_v1",
        "directives": [
            "System-level instability: prefer minimal safe verification and state capture.",
            "Delay risky mutations until runtime health is confirmed.",
        ],
        "required_prechecks": ["runtime_health_probe"],
        "avoid_actions": ["high_risk_mutation"],
    },
}

_SUBCATEGORY_OVERLAYS: Dict[str, Dict[str, Any]] = {
    "plan_execution_misalignment": {
        "directives": [
            "Plan-execution misalignment: keep step description tool-specific and enforce tool-name consistency at execution time.",
            "If explicit tool step fails alignment, retry with corrected tool call before broader fallback.",
        ],
        "required_prechecks": ["tool_alignment_check", "delta_explanation"],
        "avoid_actions": ["cross_family_tool_substitution_without_alignment"],
    },
    "shell_permission_denied": {
        "directives": [
            "Shell permission denied: avoid privileged/destructive commands until policy is confirmed.",
        ],
        "required_prechecks": ["write_policy_check"],
        "avoid_actions": ["sudo_retry_without_policy"],
    },
    "shell_command_not_found": {
        "directives": [
            "Shell command not found: verify command existence via which/type before retry.",
        ],
        "required_prechecks": ["command_exists_probe"],
        "avoid_actions": ["blind_same_command_replay"],
    },
    "browser_selector_not_found": {
        "directives": [
            "Browser selector not found: refresh UI/DOM evidence before reattempt.",
        ],
        "required_prechecks": ["browser_state_probe", "selector_probe"],
        "avoid_actions": ["same_selector_reclick"],
    },
    "browser_navigation_timeout": {
        "directives": [
            "Browser navigation timeout: split action chain and verify readiness before next hop.",
        ],
        "required_prechecks": ["timeout_probe", "browser_state_probe"],
        "avoid_actions": ["long_navigation_chain_repeat"],
    },
    "filesystem_path_not_found": {
        "directives": [
            "Filesystem path not found: re-resolve parent directory and target path first.",
        ],
        "required_prechecks": ["path_exists_probe"],
        "avoid_actions": ["blind_write_retry"],
    },
}


def _build_prompt_patch(*, patch: PlanningStrategyPatch) -> str:
    lines: List[str] = ["PLANNING STRATEGY PATCH:"]
    lines.append(f"- patch_id: {patch.patch_id}")
    lines.append(f"- failure_category: {patch.category}")
    for d in patch.directives[:4]:
        lines.append(f"- directive: {d}")
    if patch.required_prechecks:
        lines.append("- required_prechecks: " + ", ".join(patch.required_prechecks[:6]))
    if patch.avoid_actions:
        lines.append("- avoid_actions: " + ", ".join(patch.avoid_actions[:6]))
    lines.append("- You must show how this plan changes behavior versus the failed path.")
    return "\n".join(lines)


def derive_planning_strategy_patch(*, context: Dict[str, Any]) -> Optional[PlanningStrategyPatch]:
    if not _env_bool("QUENTIN_PLANNER_STRATEGY_PATCH_ENABLED", True):
        return None

    ctx = context or {}
    eval_data = ctx.get("last_attempt_evaluation") if isinstance(ctx.get("last_attempt_evaluation"), dict) else {}
    category = str(eval_data.get("category") or "").strip().lower()
    subcategory = str(eval_data.get("error_subcategory") or "").strip().lower()
    stage = str(((ctx.get("planner_lifecycle_payload") or {}) if isinstance(ctx.get("planner_lifecycle_payload"), dict) else {}).get("stage") or "").strip().lower()

    # If QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS is explicitly set, treat it as an allowlist.
    # This is used by tests and by operators to limit patch injection surface.
    raw_targets = os.getenv("QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS")
    if raw_targets is None:
        targets = list(_PATCH_LIBRARY.keys())
    else:
        targets = _env_csv(
            "QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS",
            "plan_execution_misalignment,environment_timeout_error,tool_execution_error,model_syntax_error,logic_path_error,mixed,system_error",
        )
    allow_all = "*" in targets
    # Safety/robustness: always allow the plan-execution alignment patch even if filtered out,
    # since misalignment causes repeated wasted tool calls and is a P0 reliability issue.
    target_match = bool(allow_all or (category and category in targets) or category == "plan_execution_misalignment")

    patch_def = _PATCH_LIBRARY.get(category) if target_match else None
    if patch_def is not None:
        patch = PlanningStrategyPatch(
            patch_id=str(patch_def.get("patch_id") or "category_patch_v1"),
            category=category,
            directives=[str(x) for x in (patch_def.get("directives") or []) if str(x).strip()],
            required_prechecks=[str(x) for x in (patch_def.get("required_prechecks") or []) if str(x).strip()],
            avoid_actions=[str(x) for x in (patch_def.get("avoid_actions") or []) if str(x).strip()],
            reason=f"category={category}",
        )
        overlay = _SUBCATEGORY_OVERLAYS.get(subcategory) if subcategory else None
        if isinstance(overlay, dict):
            patch.directives.extend([str(x) for x in (overlay.get("directives") or []) if str(x).strip()])
            patch.required_prechecks.extend([str(x) for x in (overlay.get("required_prechecks") or []) if str(x).strip()])
            patch.avoid_actions.extend([str(x) for x in (overlay.get("avoid_actions") or []) if str(x).strip()])
            patch.required_prechecks = sorted({x for x in patch.required_prechecks if x})
            patch.avoid_actions = sorted({x for x in patch.avoid_actions if x})
            patch.reason = f"category={category}, subcategory={subcategory}"
        patch.prompt_patch = _build_prompt_patch(patch=patch)
        return patch

    if not _env_bool("QUENTIN_PLANNER_STRATEGY_PATCH_FALLBACK_ENABLED", True):
        return None
    if stage not in {"retry", "stuck"}:
        return None

    fallback = PlanningStrategyPatch(
        patch_id="generic_retry_replan_v1",
        category=category or "unknown",
        directives=[
            "Retry/stuck fallback patch: force one discovery probe before any risky change.",
            "Do not replay the exact same tool-call sequence from previous attempt.",
        ],
        required_prechecks=["env_diagnostics"],
        avoid_actions=["same_strategy_replay"],
        reason=f"fallback_for_stage={stage}",
    )
    fallback.prompt_patch = _build_prompt_patch(patch=fallback)
    return fallback
