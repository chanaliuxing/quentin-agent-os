from __future__ import annotations

from typing import Any, Dict, List, Optional

from quentin.meta.capability_gap import CapabilityGap, CapabilityGapEvidence


def _tool_result_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            out = obj.to_dict()
            if isinstance(out, dict):
                return out
        except Exception:
            return {"repr": repr(obj)}
    if hasattr(obj, "model_dump"):
        try:
            out = obj.model_dump()
            if isinstance(out, dict):
                return out
        except Exception:
            return {"repr": repr(obj)}
    if hasattr(obj, "dict"):
        try:
            out = obj.dict()
            if isinstance(out, dict):
                return out
        except Exception:
            return {"repr": repr(obj)}
    return {"repr": repr(obj)}


def extract_capability_gaps_from_exec_steps(
    *,
    step_records: List[Dict[str, Any]],
    domain: str,
    environment: str,
    trace_id: Optional[str] = None,
) -> List[CapabilityGap]:
    """
    Extract capability gaps from executor step records (best-effort).

    v0 extracts:
    - tool_not_found: tool_manager couldn't resolve a tool handler
    - tool_blocked: permission/policy disabled
    """
    gaps: List[CapabilityGap] = []
    for step in step_records or []:
        if not isinstance(step, dict):
            continue
        res = step.get("result")
        if not isinstance(res, dict):
            continue
        tool_res = _tool_result_to_dict(res.get("tool_result"))
        if not tool_res:
            continue
        err = str(tool_res.get("error") or "").strip()
        if not err:
            continue

        tool_name = str(tool_res.get("tool_name") or "").strip() or None
        evidence = []
        if trace_id:
            evidence.append(CapabilityGapEvidence(type="trace", ref=str(trace_id)))
        evidence.append(CapabilityGapEvidence(type="tool_error", ref=tool_name or "unknown", details={"error": err}))

        if "tool_not_found" in err or "tool not found" in err:
            gaps.append(
                CapabilityGap.new(
                    gap_type="tool_not_found",
                    gap_text=f"tool not found: {tool_name or 'unknown'}",
                    tool_name=tool_name,
                    domain=domain,
                    environment=environment,
                    evidence=evidence,
                    meta={"executor_step_id": step.get("step_id")},
                )
            )
        elif "tool blocked" in err or "tool disabled" in err:
            gaps.append(
                CapabilityGap.new(
                    gap_type="tool_blocked",
                    gap_text=f"tool blocked/disabled: {tool_name or 'unknown'}",
                    tool_name=tool_name,
                    domain=domain,
                    environment=environment,
                    evidence=evidence,
                    meta={"executor_step_id": step.get("step_id")},
                )
            )
    return gaps

