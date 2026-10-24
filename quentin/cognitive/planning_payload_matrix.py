from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PlannerLifecyclePayload:
    stage: str  # initial | retry | stuck
    state_machine: str = "planner_payload_matrix_v1"
    attempt_band: str = "early"
    directives: List[str] = field(default_factory=list)
    force_speculative_execution: bool = False
    force_progress_sync: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def derive_planner_lifecycle_payload(*, context: Dict[str, Any]) -> PlannerLifecyclePayload:
    if not _env_bool("QUENTIN_PLANNER_PAYLOAD_MATRIX_ENABLED", True):
        return PlannerLifecyclePayload(stage="initial", directives=[], reason="matrix_disabled")

    ctx = context or {}
    failure_count = int(ctx.get("failure_count") or 0)
    tool_only_no_update_count = int(ctx.get("tool_only_no_update_count") or 0)
    attempt_index = int(ctx.get("attempt_index") or 1)
    eval_data = ctx.get("last_attempt_evaluation") if isinstance(ctx.get("last_attempt_evaluation"), dict) else {}
    category = str(eval_data.get("category") or "").strip().lower()
    has_loop_signal = category in {"logic_path_error", "plan_execution_misalignment", "mixed"} or tool_only_no_update_count >= 2
    progress_sync_trigger = tool_only_no_update_count >= 3

    retry_threshold = max(1, int(os.getenv("QUENTIN_PLANNER_RETRY_THRESHOLD", "1") or "1"))
    stuck_threshold = max(2, int(os.getenv("QUENTIN_PLANNER_STUCK_THRESHOLD", "3") or "3"))
    force_spec = _env_bool("QUENTIN_PLANNER_FORCE_SPECULATIVE_ON_STUCK", True)
    escalation_enabled = _env_bool("QUENTIN_PLANNER_PAYLOAD_ESCALATION_ENABLED", True)
    if attempt_index >= 5:
        attempt_band = "late"
    elif attempt_index >= 3:
        attempt_band = "mid"
    else:
        attempt_band = "early"

    if failure_count >= stuck_threshold or has_loop_signal:
        directives = [
            "STUCK MODE: Stop repeating the same strategy.",
            "Enable speculative execution: propose 2 hypotheses and attach one cheap probe each.",
            "Prioritize environment diagnostics (pwd/ls/id/fs.get_write_policy) before mutation.",
        ]
        if progress_sync_trigger:
            directives.append(
                "TOOL FEEDBACK TURN LIMIT HIT: before more tool calls, include a user-visible progress sync step."
            )
        if escalation_enabled and attempt_band == "late":
            directives.extend(
                [
                    "LATE RETRY ESCALATION: hard reset decomposition and avoid inherited failed branch.",
                    "Mandatory user-visible status update before next mutating tool action.",
                ]
            )
        return PlannerLifecyclePayload(
            stage="stuck",
            attempt_band=attempt_band,
            directives=directives,
            force_speculative_execution=force_spec,
            force_progress_sync=(progress_sync_trigger or (escalation_enabled and attempt_band == "late")),
            reason=f"failure_count={failure_count}, loop_signal={has_loop_signal}",
        )

    if failure_count >= retry_threshold or attempt_index > 1:
        directives = [
            "RETRY MODE: Compare latest error with previous attempt and explain deltas.",
            "Do not repeat identical tool call + args sequence.",
            "Tighten prechecks before write/delete/install steps.",
        ]
        if escalation_enabled and attempt_band == "mid":
            directives.append("MID RETRY ESCALATION: constrain scope to bounded diagnostics + one minimal mutation.")
        if escalation_enabled and attempt_band == "late":
            directives.extend(
                [
                    "LATE RETRY ESCALATION: force decomposition reset and prohibit old branch replay.",
                    "Before new tool calls, report progress and explicit strategy delta to user.",
                ]
            )
        return PlannerLifecyclePayload(
            stage="retry",
            attempt_band=attempt_band,
            directives=directives,
            force_progress_sync=(escalation_enabled and attempt_band == "late"),
            reason=f"attempt_index={attempt_index}, failure_count={failure_count}",
        )

    return PlannerLifecyclePayload(
        stage="initial",
        attempt_band=attempt_band,
        directives=[
            "INITIAL MODE: Exploration-first planning.",
            "Map unknowns with discovery steps before risky operations.",
            "Prefer reversible, low-risk, minimal diffs.",
        ],
        reason="first_attempt",
    )
