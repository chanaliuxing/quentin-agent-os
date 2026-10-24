from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RetryPlanDelta:
    previous_step_count: int
    changed_strategy: bool
    dropped_step_ids: List[str]
    reason: str = ""
    prompt_patch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_step_text(step: Dict[str, Any]) -> str:
    return str(step.get("description") or "").strip().lower()


def derive_retry_plan_delta(
    *,
    attempt_index: int,
    previous_plan_steps: Optional[List[Dict[str, Any]]],
    last_exec_result: Dict[str, Any],
) -> Optional[RetryPlanDelta]:
    if int(attempt_index or 1) <= 1:
        return None
    prev = [dict(s) for s in (previous_plan_steps or []) if isinstance(s, dict)]
    if not prev:
        return None

    dropped = [str(s.get("step_id") or "").strip() for s in prev[:8] if str(s.get("step_id") or "").strip()]
    eval_data = last_exec_result.get("attempt_evaluation") if isinstance(last_exec_result, dict) else {}
    category = str((eval_data or {}).get("category") or "").strip().lower()
    previous_error = ""
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    if isinstance(raw, dict):
        previous_error = str(raw.get("error") or "").strip()
    if not previous_error:
        previous_error = str(last_exec_result.get("error") or "").strip()

    reason = f"retry_after={category or 'unknown_error'}"
    patch_lines = [
        "RETRY PLAN DELTA:",
        f"- previous_step_count: {len(prev)}",
        f"- dropped_or_reworked_step_ids: {', '.join(dropped) if dropped else '(none)'}",
        f"- previous_error: {previous_error[:300] if previous_error else '(unknown)'}",
        f"- failure_category: {category or 'unknown'}",
        "- Requirement: include at least one alternative branch/probe that was not in previous failed plan.",
        "- Requirement: explicitly explain one delta between this plan and previous plan.",
    ]
    return RetryPlanDelta(
        previous_step_count=len(prev),
        changed_strategy=True,
        dropped_step_ids=dropped,
        reason=reason,
        prompt_patch="\n".join(patch_lines),
    )
