from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PlannerPayloadVariant:
    variant_id: str
    stage: str
    attempt_band: str
    category: str
    tool_family: str
    directives: List[str] = field(default_factory=list)
    required_prechecks: List[str] = field(default_factory=list)
    prompt_patch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _infer_tool_family(last_exec_result: Dict[str, Any]) -> str:
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        res = step.get("result") if isinstance(step.get("result"), dict) else {}
        call_tool = res.get("call_tool") if isinstance(res.get("call_tool"), dict) else {}
        tool_name = str(call_tool.get("tool_name") or "").strip().lower()
        if not tool_name:
            continue
        if tool_name.startswith("shell."):
            return "shell"
        if tool_name.startswith("browser.") or tool_name.startswith("web."):
            return "browser"
        if tool_name.startswith("fs."):
            return "filesystem"
    return "generic"


def _build_prompt_patch(v: PlannerPayloadVariant) -> str:
    lines = [
        "PLANNER PAYLOAD VARIANT PATCH:",
        f"- variant_id: {v.variant_id}",
        f"- stage: {v.stage}",
        f"- attempt_band: {v.attempt_band}",
        f"- category: {v.category}",
        f"- tool_family: {v.tool_family}",
    ]
    for d in v.directives[:4]:
        lines.append(f"- directive: {d}")
    if v.required_prechecks:
        lines.append("- required_prechecks: " + ", ".join(v.required_prechecks[:6]))
    return "\n".join(lines)


def derive_planner_payload_variant(*, context: Dict[str, Any]) -> Dict[str, Any]:
    if not _env_bool("QUENTIN_PLANNER_PAYLOAD_VARIANTS_ENABLED", True):
        return {}
    ctx = context or {}
    lifecycle = ctx.get("planner_lifecycle_payload") if isinstance(ctx.get("planner_lifecycle_payload"), dict) else {}
    stage = str(lifecycle.get("stage") or "initial").strip().lower() or "initial"
    attempt_band = str(lifecycle.get("attempt_band") or "early").strip().lower() or "early"
    eval_data = ctx.get("last_attempt_evaluation") if isinstance(ctx.get("last_attempt_evaluation"), dict) else {}
    category = str(eval_data.get("category") or "unknown").strip().lower() or "unknown"
    error_subcategory = str(eval_data.get("error_subcategory") or "").strip().lower()
    tool_family = _infer_tool_family(ctx.get("last_exec_result") if isinstance(ctx.get("last_exec_result"), dict) else {})

    directives: List[str] = []
    prechecks: List[str] = []

    if tool_family == "shell":
        directives += [
            "Shell-failure mode: avoid replaying the same command head + args.",
            "Use pwd/id/ls diagnostics before shell mutation commands.",
        ]
        prechecks += ["shell_diag"]
        if error_subcategory == "shell_permission_denied":
            directives.append("Shell permission-denied: verify user/write policy and avoid privileged commands.")
            prechecks.append("write_policy_check")
        elif error_subcategory == "shell_command_not_found":
            directives.append("Shell command-not-found: probe command availability with which/type before rerun.")
            prechecks.append("command_exists_probe")
    elif tool_family == "browser":
        directives += [
            "Browser-failure mode: re-acquire page state before click/type.",
            "Verify selector/page readiness before repeating UI action.",
        ]
        prechecks += ["browser_state_probe", "selector_probe"]
        if error_subcategory == "browser_navigation_timeout":
            directives.append("Browser navigation-timeout: verify page readiness and reduce action chain length.")
            prechecks.append("timeout_probe")
        elif error_subcategory == "browser_selector_not_found":
            directives.append("Browser selector-not-found: inspect current DOM/UI tree before next click/type.")
            prechecks.append("selector_probe")
    elif tool_family == "filesystem":
        directives += [
            "Filesystem-failure mode: verify path and write policy before mutation.",
            "Prefer fs.read_file/fs.search_replace over blind fs.write_file retries.",
        ]
        prechecks += ["path_exists_probe", "write_policy_check"]
        if error_subcategory == "filesystem_path_not_found":
            directives.append("Filesystem path-not-found: confirm exact parent/file path before edits.")
        elif error_subcategory == "filesystem_permission_denied":
            directives.append("Filesystem permission-denied: remap target path to allowed writable roots.")
            prechecks.append("write_policy_check")

    if stage == "retry":
        directives.append("Retry stage: include explicit delta from failed attempt.")
        prechecks.append("delta_explanation")
    elif stage == "stuck":
        directives.append("Stuck stage: force alternative branch with two cheap probes.")
        prechecks.append("branch_probe")

    if attempt_band == "mid":
        directives.append("Attempt band mid: keep retry bounded; avoid broad refactors.")
    elif attempt_band == "late":
        directives.append("Attempt band late: mandatory strategy reset + progress sync before mutation.")
        prechecks += ["delta_explanation", "branch_probe", "progress_sync"]

    if category == "environment_timeout_error":
        directives.append("Timeout class: keep probes bounded and low-cost.")
        prechecks.append("timeout_probe")
    elif category == "model_syntax_error":
        directives.append("Syntax class: enforce strict output schema and short atomic steps.")
        prechecks.append("schema_guard")
    elif error_subcategory == "plan_execution_misalignment":
        directives.append("Misalignment class: ensure explicit step tool names match executor tool calls.")
        prechecks += ["tool_alignment_check", "delta_explanation"]

    sub = error_subcategory or "na"
    variant_id = f"pv_{stage}_{tool_family}_{category}_{sub}_v1"
    variant = PlannerPayloadVariant(
        variant_id=variant_id,
        stage=stage,
        attempt_band=attempt_band,
        category=category,
        tool_family=tool_family,
        directives=directives,
        required_prechecks=sorted({x for x in prechecks if x}),
    )
    variant.prompt_patch = _build_prompt_patch(variant)
    return variant.to_dict()
