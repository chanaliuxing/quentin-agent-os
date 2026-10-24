from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import re
from collections import Counter


def _normalize_tool_family(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("fs."):
        return "fs."
    if raw.startswith("shell."):
        return "shell."
    if raw.startswith("browser."):
        return "browser."
    if raw.startswith("web_search."):
        return "web_search."

    alias_map = {
        "ls": "fs.",
        "mkdir": "fs.",
        "cat": "fs.",
        "find": "shell.",
        "read_file": "fs.",
        "write_file": "fs.",
        "pwd": "shell.",
        "id": "shell.",
        "bash": "shell.",
        "sh": "shell.",
        "zsh": "shell.",
        "click": "browser.",
        "navigate": "browser.",
        "open_url": "browser.",
        "search": "web_search.",
    }
    return alias_map.get(raw, "")


def _normalize_tool_id(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return ""

    alias_map = {
        "ls": "fs.list_dir",
        "list_dir": "fs.list_dir",
        "fs.list_dir": "fs.list_dir",
        "cat": "fs.read_file",
        "read_file": "fs.read_file",
        "fs.read_file": "fs.read_file",
        "write_file": "fs.write_file",
        "fs.write_file": "fs.write_file",
        "mkdir": "fs.mkdir",
        "fs.mkdir": "fs.mkdir",
        "exists": "fs.exists",
        "fs.exists": "fs.exists",
        "pwd": "shell.run_command",
        "id": "shell.run_command",
        "bash": "shell.run_command",
        "sh": "shell.run_command",
        "zsh": "shell.run_command",
        "which": "shell.run_command",
        "grep": "shell.run_command",
        "find": "shell.run_command",
        "shell.run_command": "shell.run_command",
        "click": "browser.click",
        "browser.click": "browser.click",
        "navigate": "browser.navigate",
        "open_url": "browser.navigate",
        "browser.navigate": "browser.navigate",
        "search": "web_search.search",
        "web_search.search": "web_search.search",
    }
    if raw in alias_map:
        return alias_map[raw]
    return raw


def _command_head_from_args(args: Any) -> str:
    obj = args if isinstance(args, dict) else {}
    command = str(obj.get("command") or "").strip().lower()
    if not command:
        return ""
    return command.split()[0].split("/")[-1]


def _normalize_actual_tool_id(*, tool_name: str, result_obj: Dict[str, Any], tool_result_obj: Dict[str, Any]) -> str:
    """
    Normalize runtime tool identity into an exact-match id.

    Cross-runtime parity:
    - shell.run_command + `cat` -> fs.read_file
    - shell.run_command + `ls`  -> fs.list_dir
    - shell.run_command + `mkdir` -> fs.mkdir
    """
    normalized = _normalize_tool_id(tool_name)
    if normalized != "shell.run_command":
        return normalized

    call_tool = result_obj.get("call_tool") if isinstance(result_obj.get("call_tool"), dict) else {}
    head = _command_head_from_args(call_tool.get("args") if isinstance(call_tool, dict) else {})
    if not head:
        out = tool_result_obj.get("output") if isinstance(tool_result_obj.get("output"), dict) else {}
        head = _command_head_from_args(out)
    if head in {"cat", "type"}:
        return "fs.read_file"
    if head in {"ls", "dir"}:
        return "fs.list_dir"
    if head in {"mkdir"}:
        return "fs.mkdir"
    if head in {"find", "grep", "which", "pwd", "id"}:
        return "shell.run_command"
    return normalized


def _extract_expected_tool_from_description(description: str) -> tuple[str, str]:
    desc = str(description or "").strip().lower()
    if not desc:
        return ("", "")

    explicit_tools = (
        "fs.exists",
        "fs.read_file",
        "fs.search_replace",
        "fs.write_file",
        "fs.get_write_policy",
        "fs.mkdir",
        "fs.list_dir",
        "shell.run_command",
        "browser.click",
        "browser.navigate",
        "web_search.search",
    )
    matched_explicit: List[str] = [tool_id for tool_id in explicit_tools if tool_id in desc]
    if matched_explicit:
        # For verification/existence phrasing, prefer `fs.exists` exact intent even when
        # write tool names appear in the same sentence (common in "if not exists then write" plans).
        verify_like = ("exist" in desc) or ("does not exist" in desc)
        if verify_like and ("fs.exists" in matched_explicit or "fs.write_file" in matched_explicit):
            return ("fs.", "fs.exists")
        # Mixed tool instructions are ambiguous for exact-match scoring; keep family only.
        if len(matched_explicit) > 1 and any(k in desc for k in ("fallback", "only if", "if needed", "if necessary", "or ")):
            fam = _normalize_tool_family(_normalize_tool_id(matched_explicit[0]))
            return (fam, "")
        canonical = _normalize_tool_id(matched_explicit[0])
        return (_normalize_tool_family(canonical), canonical)

    token_to_tool = {
        "exists": "fs.exists",
        "fs.exists": "fs.exists",
        "search_replace": "fs.search_replace",
        "fs.search_replace": "fs.search_replace",
        "read_file": "fs.read_file",
        "write_file": "fs.write_file",
        "list_dir": "fs.list_dir",
        "ls": "fs.list_dir",
        "mkdir": "fs.mkdir",
        "cat": "fs.read_file",
        "find": "shell.run_command",
        "grep": "shell.run_command",
        "which": "shell.run_command",
        "pwd": "shell.run_command",
        "id": "shell.run_command",
        "open_url": "browser.navigate",
        "click": "browser.click",
        "navigate": "browser.navigate",
    }
    for token, tool_id in token_to_tool.items():
        if re.search(rf"(^|[^a-z0-9_]){re.escape(token)}([^a-z0-9_]|$)", desc):
            canonical = _normalize_tool_id(tool_id)
            return (_normalize_tool_family(canonical), canonical)

    family_hints = (
        ("filesystem", "fs."),
        ("fs", "fs."),
        ("shell", "shell."),
        ("browser", "browser."),
        ("web_search", "web_search."),
    )
    for key, fam in family_hints:
        if key in desc:
            return (fam, "")
    return ("", "")


def _read_jsonl(path: Path, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    if limit is not None and limit > 0:
        return rows[-limit:]
    return rows


def _attempt_band_from_index(attempt_index: int) -> str:
    idx = int(attempt_index or 0)
    if idx <= 2:
        return "early"
    if idx <= 4:
        return "mid"
    return "late"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _extract_plan_signature(payload: Dict[str, Any]) -> str:
    """
    Best-effort compact plan signature used to detect reset oscillation.
    """
    plan = payload.get("plan") if isinstance(payload.get("plan"), list) else []
    if plan:
        first = plan[0] if isinstance(plan[0], dict) else {}
        return str(first.get("description") or first.get("step_id") or "").strip().lower()[:200]
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    if steps:
        first = steps[0] if isinstance(steps[0], dict) else {}
        return str(first.get("description") or first.get("step_id") or "").strip().lower()[:200]
    ro = str(payload.get("raw_output") or "").strip().lower()
    if ro:
        return ro[:200]
    repairs = payload.get("planner_repairs") if isinstance(payload.get("planner_repairs"), list) else []
    if repairs:
        return ",".join(str(x).strip().lower() for x in repairs[:4])
    return ""


def _extract_legacy_planning_metadata(payload: Dict[str, Any]) -> Dict[str, str]:
    raw_output = str(payload.get("raw_output") or "")
    out: Dict[str, str] = {"source": "", "reason": "", "subcategory": ""}
    if not raw_output:
        return out

    source = ""
    reason = ""
    m_source = re.search(r'"source"\s*:\s*"([^"]+)"', raw_output, re.IGNORECASE)
    if m_source:
        source = str(m_source.group(1) or "").strip().lower()
    m_reason = re.search(r'"reason"\s*:\s*"([^"]+)"', raw_output, re.IGNORECASE)
    if m_reason:
        reason = str(m_reason.group(1) or "").strip().lower()
    if not reason:
        m_note = re.search(r"antipattern_recovery:([a-z0-9_]+)", raw_output, re.IGNORECASE)
        if m_note:
            reason = str(m_note.group(1) or "").strip().lower()
            if not source:
                source = "antipattern_recovery"

    subcategory = reason
    out["source"] = source
    out["reason"] = reason
    out["subcategory"] = subcategory
    return out


def _derive_planning_diag(payload: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    ctxi = payload.get("context_injected") if isinstance(payload.get("context_injected"), dict) else {}
    diag = ctxi.get("planning_diagnostics") if isinstance(ctxi.get("planning_diagnostics"), dict) else {}
    if diag:
        return dict(diag), False

    attempt_index = int(payload.get("attempt_index") or 0)
    planner_repairs = payload.get("planner_repairs") if isinstance(payload.get("planner_repairs"), list) else []
    legacy = _extract_legacy_planning_metadata(payload)
    source = str(legacy.get("source") or "").strip().lower()
    reason = str(legacy.get("reason") or "").strip().lower()
    subcategory = str(legacy.get("subcategory") or "").strip().lower()

    attempt_stage = "initial"
    if attempt_index >= 4:
        attempt_stage = "stuck"
    elif attempt_index >= 2:
        attempt_stage = "retry"
    if source == "antipattern_recovery" and attempt_stage == "initial":
        attempt_stage = "retry"

    variant_id = ""
    if source or subcategory:
        source_key = source or "legacy"
        sub_key = subcategory or "unknown"
        variant_id = f"pv_legacy_{source_key}_{sub_key}_v1"

    strategy_patch_id = source or ("legacy_patch_v1" if variant_id else "")
    retry_delta_reason = f"legacy_retry_after={reason}" if reason else ""

    inferred = {
        "attempt_stage": attempt_stage,
        "attempt_band": _attempt_band_from_index(attempt_index),
        "force_progress_sync": bool("inject_progress_sync_step" in [str(x) for x in planner_repairs]),
        "failure_category": "legacy",
        "error_subcategory": subcategory,
        "strategy_patch_id": strategy_patch_id,
        "strategy_patch_category": source,
        "payload_variant_id": variant_id,
        "payload_tool_family": "",
        "retry_delta_reason": retry_delta_reason,
        "legacy_inferred": True,
    }
    return inferred, True


def build_intelligence_audit(
    *,
    repo_root: str | Path = ".",
    limit: int = 20000,
    adaptive_alias: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    events = _read_jsonl(root / "data" / "traces" / "events.jsonl", limit=limit)
    audits = _read_jsonl(root / "data" / "audit_events.jsonl", limit=limit * 2)

    planning_events = [e for e in events if str(e.get("event_type") or "") == "planning"]
    planning_by_trace: Dict[str, List[Dict[str, Any]]] = {}

    risky_plans = 0
    risky_without_discovery = 0
    strategy_regression_repairs = 0
    fallback_decompositions = 0
    risky_examples: List[Dict[str, Any]] = []
    planning_diag_total = 0
    planning_diag_with_variant = 0
    planning_diag_with_strategy_patch = 0
    planning_diag_with_retry_delta = 0
    planning_diag_with_subcategory = 0
    planning_diag_subcategory_aligned_variant = 0
    risky_without_diag = 0
    planning_diag_examples: List[Dict[str, Any]] = []
    progress_sync_required = 0
    progress_sync_compliant = 0
    attempt_band_required = 0
    attempt_band_present = 0
    legacy_diag_inferred = 0
    discovery_evidence_expected = 0
    discovery_evidence_found = 0
    discovery_evidence_examples: List[Dict[str, Any]] = []

    for e in planning_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        trace_id = str(e.get("trace_id") or "")
        planning_by_trace.setdefault(trace_id, []).append(
            {
                "attempt_index": int(payload.get("attempt_index") or 0),
                "signature": _extract_plan_signature(payload),
            }
        )
        dg = payload.get("discovery_guard") if isinstance(payload.get("discovery_guard"), dict) else {}
        risky_steps = int(dg.get("risky_steps") or 0)
        compliant = bool(dg.get("discovery_before_risky", True))
        if risky_steps > 0:
            risky_plans += 1
            discovery_evidence_expected += 1
            first_discovery_step_id = str(dg.get("first_discovery_step_id") or "").strip()
            if first_discovery_step_id:
                discovery_evidence_found += 1
            if not compliant:
                risky_without_discovery += 1
                if len(risky_examples) < 5:
                    risky_examples.append(
                        {
                            "trace_id": str(e.get("trace_id") or ""),
                            "first_risky_step_id": str(dg.get("first_risky_step_id") or ""),
                            "first_discovery_step_id": str(dg.get("first_discovery_step_id") or ""),
                        }
                    )
            if not first_discovery_step_id and len(discovery_evidence_examples) < 5:
                discovery_evidence_examples.append(
                    {
                        "trace_id": str(e.get("trace_id") or ""),
                        "first_risky_step_id": str(dg.get("first_risky_step_id") or ""),
                    }
                )
        diag, inferred = _derive_planning_diag(payload)
        if inferred:
            legacy_diag_inferred += 1
        attempt_index = int(payload.get("attempt_index") or 0)
        if attempt_index >= 3:
            attempt_band_required += 1
        if risky_steps > 0 and not diag:
            risky_without_diag += 1
        if isinstance(diag, dict) and diag:
            planning_diag_total += 1
            variant_id = str(diag.get("payload_variant_id") or "").strip()
            strategy_patch_id = str(diag.get("strategy_patch_id") or "").strip()
            retry_delta_reason = str(diag.get("retry_delta_reason") or "").strip()
            subcategory = str(diag.get("error_subcategory") or "").strip().lower()
            if variant_id:
                planning_diag_with_variant += 1
            if strategy_patch_id:
                planning_diag_with_strategy_patch += 1
            if retry_delta_reason:
                planning_diag_with_retry_delta += 1
            if subcategory:
                planning_diag_with_subcategory += 1
                if subcategory in variant_id.lower():
                    planning_diag_subcategory_aligned_variant += 1
            if len(planning_diag_examples) < 5:
                planning_diag_examples.append(
                    {
                        "trace_id": str(e.get("trace_id") or ""),
                        "payload_variant_id": variant_id,
                        "error_subcategory": subcategory,
                        "strategy_patch_id": strategy_patch_id,
                    }
                )
            if attempt_index >= 3 and str(diag.get("attempt_band") or "").strip():
                attempt_band_present += 1
            if bool(diag.get("force_progress_sync", False)):
                progress_sync_required += 1
                repairs = payload.get("planner_repairs") if isinstance(payload.get("planner_repairs"), list) else []
                raw_output = str(payload.get("raw_output") or "")
                if (
                    "inject_progress_sync_step" in [str(x) for x in repairs]
                    or ("progress sync" in raw_output.lower())
                    or ("status update" in raw_output.lower())
                ):
                    progress_sync_compliant += 1

        repairs = payload.get("planner_repairs") if isinstance(payload.get("planner_repairs"), list) else []
        if "prevent_strategy_regression_reused_previous_decomposition" in repairs:
            strategy_regression_repairs += 1
        if "decompose_single_step_fallback" in repairs:
            fallback_decompositions += 1

    weak_reasoning_detected = 0
    weak_reasoning_resolved = 0
    weak_reasoning_fallback = 0
    blocked_actions: Dict[str, int] = {}
    known_actions = ("nano", "vim", "vi", "emacs", "wget", "curl", "man", "less", "more")
    p_interactive = re.compile(r"interactive command ['\"]?([a-zA-Z0-9._/-]+)['\"]?")

    for a in audits:
        event_type = str(a.get("event_type") or "")
        phase = str(a.get("phase") or "")
        payload = a.get("payload") if isinstance(a.get("payload"), dict) else {}

        if event_type == "done_council_quality":
            if phase == "weak_reasoning_detected":
                weak_reasoning_detected += 1
            elif phase == "retry_improved":
                weak_reasoning_resolved += 1
            elif phase == "fallback_reason_applied":
                weak_reasoning_fallback += 1

        if phase in {"denied", "error"}:
            action_text = str(payload.get("command") or payload.get("action") or payload.get("tool_name") or "").strip().lower()
            if not action_text:
                txt = (
                    f"{payload.get('reason', '')} {payload.get('error', '')} "
                    f"{payload.get('command_head', '')} {json.dumps(payload, ensure_ascii=False)}"
                ).lower()
                m = p_interactive.search(txt)
                if m:
                    action_text = str(m.group(1) or "").lower()
                if not action_text:
                    for k in known_actions:
                        if re.search(rf"(^|[^a-z0-9_]){re.escape(k)}([^a-z0-9_]|$)", txt):
                            action_text = k
                            break
            if action_text:
                blocked_actions[action_text] = blocked_actions.get(action_text, 0) + 1

    repeated_blocked = {k: v for k, v in blocked_actions.items() if v >= 2}

    compliance_rate = 1.0 if risky_plans == 0 else (float(risky_plans - risky_without_discovery) / float(risky_plans))
    weak_resolution_rate = None
    if weak_reasoning_detected > 0:
        weak_resolution_rate = float(weak_reasoning_resolved) / float(weak_reasoning_detected)

    if planning_diag_total > 0:
        variant_coverage = float(planning_diag_with_variant) / float(planning_diag_total)
        patch_coverage = float(planning_diag_with_strategy_patch) / float(planning_diag_total)
        retry_delta_coverage = float(planning_diag_with_retry_delta) / float(planning_diag_total)
        subtype_alignment = (
            float(planning_diag_subcategory_aligned_variant) / float(planning_diag_with_subcategory)
            if planning_diag_with_subcategory > 0
            else 1.0
        )
        strategy_switch_effectiveness = (
            (0.35 * variant_coverage)
            + (0.30 * patch_coverage)
            + (0.20 * retry_delta_coverage)
            + (0.15 * subtype_alignment)
        )
    else:
        variant_coverage = 0.0
        patch_coverage = 0.0
        retry_delta_coverage = 0.0
        subtype_alignment = 0.0
        strategy_switch_effectiveness = 0.0

    critic_events = [e for e in events if str(e.get("event_type") or "") == "critic"]
    execution_events = [e for e in events if str(e.get("event_type") or "") == "execution"]
    interrupts_total = 0
    hard_reset_total = 0
    interrupt_resolved = 0
    hard_reset_recovered = 0
    cooldown_events = 0
    cooldown_sum = 0
    cooldown_recurrence = 0
    done_by_trace: Dict[str, bool] = {}
    interrupt_trace_ids: List[str] = []
    hard_reset_trace_ids: List[str] = []
    hard_reset_points_by_trace: Dict[str, List[int]] = {}
    critic_by_trace: Dict[str, List[Dict[str, Any]]] = {}
    attempt_eval_by_trace: Dict[str, List[Dict[str, Any]]] = {}

    for e in critic_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        trace_id = str(e.get("trace_id") or "")
        critic_by_trace.setdefault(trace_id, []).append(payload)
        if str(payload.get("action") or "").strip().lower() == "attempt_evaluated":
            attempt_eval = payload.get("attempt_evaluation") if isinstance(payload.get("attempt_evaluation"), dict) else {}
            if attempt_eval:
                attempt_eval_by_trace.setdefault(trace_id, []).append(
                    {
                        "attempt_index": int(payload.get("attempt_index") or 0),
                        "category": str(attempt_eval.get("category") or "").strip().lower(),
                        "error_subcategory": str(attempt_eval.get("error_subcategory") or "").strip().lower(),
                    }
                )
        if bool(payload.get("done", False)):
            done_by_trace[trace_id] = True
        i_state = str(payload.get("attempt_interrupt_state") or "").strip().lower()
        if i_state in {"interrupt", "hard_reset"}:
            interrupts_total += 1
            interrupt_trace_ids.append(trace_id)
            c_assigned = int(payload.get("cooldown_assigned") or 0)
            if c_assigned > 0:
                cooldown_events += 1
                cooldown_sum += c_assigned
            if i_state == "hard_reset":
                hard_reset_total += 1
                hard_reset_trace_ids.append(trace_id)
                hard_reset_points_by_trace.setdefault(trace_id, []).append(int(payload.get("attempt_index") or 0))

    for tid in interrupt_trace_ids:
        if done_by_trace.get(tid, False):
            interrupt_resolved += 1
    for tid in hard_reset_trace_ids:
        if done_by_trace.get(tid, False):
            hard_reset_recovered += 1
    # Recurrence during cooldown window: same trace receives another interrupt within assigned cooldown attempts.
    for tid, rows in critic_by_trace.items():
        interrupt_rows: List[Dict[str, Any]] = []
        for p in rows:
            st = str(p.get("attempt_interrupt_state") or "").strip().lower()
            if st in {"interrupt", "hard_reset"}:
                interrupt_rows.append(p)
        for i, p in enumerate(interrupt_rows):
            cooldown = int(p.get("cooldown_assigned") or 0)
            aidx = int(p.get("attempt_index") or 0)
            if cooldown <= 0 or aidx <= 0:
                continue
            for nxt in interrupt_rows[i + 1:]:
                naidx = int(nxt.get("attempt_index") or 0)
                if naidx <= aidx:
                    continue
                if (naidx - aidx) <= cooldown:
                    cooldown_recurrence += 1
                break

    interrupt_effectiveness = (
        float(interrupt_resolved) / float(interrupts_total)
        if interrupts_total > 0
        else 1.0
    )
    reset_recovery_rate = (
        float(hard_reset_recovered) / float(hard_reset_total)
        if hard_reset_total > 0
        else 1.0
    )
    progress_sync_compliance = (
        float(progress_sync_compliant) / float(progress_sync_required)
        if progress_sync_required > 0
        else 1.0
    )
    cooldown_mean = (float(cooldown_sum) / float(cooldown_events)) if cooldown_events > 0 else 0.0
    cooldown_recurrence_rate = (
        float(cooldown_recurrence) / float(cooldown_events)
        if cooldown_events > 0
        else 0.0
    )
    attempt_band_coverage = (
        float(attempt_band_present) / float(attempt_band_required)
        if attempt_band_required > 0
        else 1.0
    )
    discovery_evidence_coverage = (
        float(discovery_evidence_found) / float(discovery_evidence_expected)
        if discovery_evidence_expected > 0
        else 1.0
    )
    misalignment_eval_total = 0
    misalignment_recovered_within_2 = 0
    misalignment_recurred_within_2 = 0
    for tid, rows in attempt_eval_by_trace.items():
        ordered = sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda x: int(x.get("attempt_index") or 0),
        )
        for i, row in enumerate(ordered):
            cat = str(row.get("category") or "").strip().lower()
            sub = str(row.get("error_subcategory") or "").strip().lower()
            if not (cat == "plan_execution_misalignment" or sub == "plan_execution_misalignment"):
                continue
            misalignment_eval_total += 1
            recovered = False
            recurred = False
            aidx = int(row.get("attempt_index") or 0)
            for nxt in ordered[i + 1:]:
                naidx = int(nxt.get("attempt_index") or 0)
                if naidx <= aidx:
                    continue
                if naidx > (aidx + 2):
                    break
                ncat = str(nxt.get("category") or "").strip().lower()
                nsub = str(nxt.get("error_subcategory") or "").strip().lower()
                if ncat == "success":
                    recovered = True
                    break
                if ncat == "plan_execution_misalignment" or nsub == "plan_execution_misalignment":
                    recurred = True
            if recovered:
                misalignment_recovered_within_2 += 1
            if recurred:
                misalignment_recurred_within_2 += 1
    misalignment_recovered_within_2_rate = (
        float(misalignment_recovered_within_2) / float(misalignment_eval_total)
        if misalignment_eval_total > 0
        else 1.0
    )
    misalignment_recurrence_rate = (
        float(misalignment_recurred_within_2) / float(misalignment_eval_total)
        if misalignment_eval_total > 0
        else 0.0
    )
    goal_reanchor_required = 0
    goal_reanchor_success = 0
    plan_oscillation_events = 0
    for tid, reset_points in hard_reset_points_by_trace.items():
        plans = sorted(planning_by_trace.get(tid, []), key=lambda x: int(x.get("attempt_index") or 0))
        if not plans or not reset_points:
            continue
        for r in sorted(reset_points):
            prev_sig = ""
            next_sig = ""
            for p in plans:
                aidx = int(p.get("attempt_index") or 0)
                sig = str(p.get("signature") or "")
                if aidx <= r and sig:
                    prev_sig = sig
                if aidx > r and sig:
                    next_sig = sig
                    break
            if prev_sig or next_sig:
                goal_reanchor_required += 1
                if prev_sig and next_sig and prev_sig != next_sig:
                    goal_reanchor_success += 1
        # Oscillation: reset, next plan signature unchanged repeatedly.
        if len(reset_points) >= 2:
            for i in range(len(sorted(reset_points)) - 1):
                r1 = sorted(reset_points)[i]
                r2 = sorted(reset_points)[i + 1]
                s_after_r1 = ""
                s_after_r2 = ""
                for p in plans:
                    aidx = int(p.get("attempt_index") or 0)
                    sig = str(p.get("signature") or "")
                    if not sig:
                        continue
                    if aidx > r1 and not s_after_r1:
                        s_after_r1 = sig
                    if aidx > r2 and not s_after_r2:
                        s_after_r2 = sig
                if s_after_r1 and s_after_r2 and s_after_r1 == s_after_r2:
                    plan_oscillation_events += 1
    goal_reanchor_rate = (
        float(goal_reanchor_success) / float(goal_reanchor_required)
        if goal_reanchor_required > 0
        else 1.0
    )

    # Planning-vs-execution consistency proxy:
    # Prefer explicit tool/family alignment; avoid false negatives from legacy aliases.
    adaptive_alias_enabled = _env_bool("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_ENABLED", False) if adaptive_alias is None else bool(adaptive_alias)
    adaptive_alias_min_support = max(1, int(os.getenv("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_MIN_SUPPORT", "2")))
    adaptive_alias_max_entries = max(1, int(os.getenv("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_MAX_ENTRIES", "64")))
    adaptive_alias_window = max(1, int(os.getenv("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_WINDOW", "200")))
    adaptive_candidates: Counter[tuple[str, str]] = Counter()
    adaptive_alias_map: Dict[str, str] = {}
    adaptive_alias_applied = 0
    mismatch_patterns: Counter[str] = Counter()

    # Build adaptive alias candidates from recent successful steps only.
    if adaptive_alias_enabled:
        seen = 0
        for e in reversed(execution_events):
            payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
            steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
            for s in reversed(steps):
                if seen >= adaptive_alias_window:
                    break
                seen += 1
                if not isinstance(s, dict):
                    continue
                desc = str(s.get("description") or "").lower()
                expected_prefix, expected_tool = _extract_expected_tool_from_description(desc)
                if not expected_prefix or not expected_tool:
                    continue
                res = s.get("result") if isinstance(s.get("result"), dict) else {}
                if str(res.get("status") or "").strip().lower() not in {"ok", "success", ""}:
                    continue
                fb_tail = res.get("feedback_tail") if isinstance(res.get("feedback_tail"), list) else []
                if any(str((fb or {}).get("reason") or "").strip().lower() == "plan_execution_misalignment" for fb in fb_tail if isinstance(fb, dict)):
                    continue
                call_tool = res.get("call_tool") if isinstance(res.get("call_tool"), dict) else {}
                tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
                raw_tool_name = str(call_tool.get("tool_name") or tr.get("tool_name") or "").strip().lower()
                actual = _normalize_actual_tool_id(tool_name=raw_tool_name, result_obj=res, tool_result_obj=tr)
                if not actual:
                    continue
                expected_exact = _normalize_tool_id(expected_tool)
                if not expected_exact:
                    continue
                # Candidate only when family aligns but exact differs.
                if _normalize_tool_family(expected_exact) == _normalize_tool_family(actual) and expected_exact != actual:
                    adaptive_candidates[(expected_exact, actual)] += 1
            if seen >= adaptive_alias_window:
                break
        for (expected_exact, actual), cnt in adaptive_candidates.most_common():
            if cnt < adaptive_alias_min_support:
                continue
            if expected_exact in adaptive_alias_map:
                continue
            adaptive_alias_map[expected_exact] = actual
            if len(adaptive_alias_map) >= adaptive_alias_max_entries:
                break

    plan_exec_total = 0
    plan_exec_match = 0
    plan_exec_exact_total = 0
    plan_exec_exact_match = 0
    plan_exec_expected_steps = 0
    plan_exec_with_call_tool = 0
    plan_exec_with_tool_result = 0
    plan_exec_with_any_actual = 0
    plan_tool_alignment_events = 0
    plan_tool_alignment_blocked = 0
    plan_tool_alignment_rewrites = 0
    plan_exec_examples: List[Dict[str, Any]] = []
    for e in execution_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        for s in steps:
            if not isinstance(s, dict):
                continue
            desc = str(s.get("description") or "").lower()
            expected_prefix, expected_tool = _extract_expected_tool_from_description(desc)
            if not expected_prefix:
                continue
            plan_exec_expected_steps += 1
            res = s.get("result") if isinstance(s.get("result"), dict) else {}
            fb_tail = res.get("feedback_tail") if isinstance(res.get("feedback_tail"), list) else []
            for fb in fb_tail[-8:]:
                if not isinstance(fb, dict):
                    continue
                reason = str(fb.get("reason") or "").strip().lower()
                ev_type = str(fb.get("type") or "").strip().lower()
                if reason == "plan_execution_misalignment":
                    plan_tool_alignment_events += 1
                    if bool(fb.get("blocked")):
                        plan_tool_alignment_blocked += 1
                    if ev_type == "tool_alignment_rewrite":
                        plan_tool_alignment_rewrites += 1
            call_tool = res.get("call_tool") if isinstance(res.get("call_tool"), dict) else {}
            tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
            call_tool_name = str(call_tool.get("tool_name") or "").strip().lower()
            tool_result_name = str(tr.get("tool_name") or "").strip().lower()
            command_evidence = False
            if call_tool_name == "shell.run_command":
                command_evidence = bool(str((call_tool.get("args") or {}).get("command") or "").strip())
            if tool_result_name == "shell.run_command":
                output_obj = tr.get("output") if isinstance(tr.get("output"), dict) else {}
                if str(output_obj.get("command") or "").strip():
                    command_evidence = True
            if call_tool_name:
                plan_exec_with_call_tool += 1
            if tool_result_name:
                plan_exec_with_tool_result += 1
            raw_tool_name = call_tool_name
            if not raw_tool_name:
                raw_tool_name = tool_result_name
            actual = _normalize_actual_tool_id(
                tool_name=raw_tool_name,
                result_obj=res,
                tool_result_obj=tr,
            )
            if not actual:
                continue
            plan_exec_with_any_actual += 1
            actual_family = _normalize_tool_family(actual)
            plan_exec_total += 1
            if actual.startswith(expected_prefix) or actual_family == expected_prefix:
                plan_exec_match += 1
                is_family_mismatch = False
            elif len(plan_exec_examples) < 5:
                is_family_mismatch = True
                plan_exec_examples.append(
                    {
                        "trace_id": str(e.get("trace_id") or ""),
                        "expected_prefix": expected_prefix,
                        "actual_tool": actual,
                        "step_id": str(s.get("step_id") or ""),
                    }
                )
            else:
                is_family_mismatch = True
            if expected_tool:
                plan_exec_exact_total += 1
                expected_exact = _normalize_tool_id(expected_tool)
                exact_match = expected_exact == actual
                # Cross-runtime exact alias: existence checks often run via ls/list_dir.
                if (not exact_match) and expected_exact == "fs.exists" and actual in {"fs.list_dir", "shell.run_command"}:
                    exact_match = True
                if (not exact_match) and adaptive_alias_enabled:
                    if adaptive_alias_map.get(expected_exact) == actual:
                        exact_match = True
                        adaptive_alias_applied += 1
                if exact_match:
                    plan_exec_exact_match += 1
                if is_family_mismatch and not exact_match:
                    ignore_mismatch = False
                    if expected_exact == "fs.exists" and actual == "shell.run_command" and not command_evidence:
                        ignore_mismatch = True
                    if expected_prefix == "shell." and actual in {
                        "fs.list_dir",
                        "ls",
                        "fs.read_file",
                        "cat",
                        "fs.mkdir",
                        "mkdir",
                        "fs.exists",
                    }:
                        ignore_mismatch = True
                    if expected_prefix == "fs." and actual == "shell.run_command" and not command_evidence:
                        ignore_mismatch = True
                    if not ignore_mismatch:
                        mismatch_patterns[f"{expected_prefix}->{actual}"] += 1
    plan_execution_consistency_rate = (
        float(plan_exec_match) / float(plan_exec_total)
        if plan_exec_total > 0
        else 1.0
    )
    plan_execution_exact_match_rate = (
        float(plan_exec_exact_match) / float(plan_exec_exact_total)
        if plan_exec_exact_total > 0
        else 1.0
    )
    if plan_exec_exact_total > 0:
        plan_execution_consistency_rate = (0.70 * plan_execution_consistency_rate) + (
            0.30 * plan_execution_exact_match_rate
        )
    plan_execution_call_tool_coverage = (
        float(plan_exec_with_call_tool) / float(plan_exec_expected_steps)
        if plan_exec_expected_steps > 0
        else 1.0
    )
    plan_execution_tool_result_coverage = (
        float(plan_exec_with_tool_result) / float(plan_exec_expected_steps)
        if plan_exec_expected_steps > 0
        else 1.0
    )
    plan_execution_observed_coverage = (
        float(plan_exec_with_any_actual) / float(plan_exec_expected_steps)
        if plan_exec_expected_steps > 0
        else 1.0
    )

    plan_tool_alignment_trace_events = 0
    plan_tool_alignment_trace_blocked = 0
    plan_tool_alignment_trace_rewrites = 0
    for e in events:
        et = str(e.get("event_type") or "").strip().lower()
        if et not in {"execution", "decision"}:
            continue
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if str(payload.get("signal") or "").strip().lower() != "plan_tool_alignment":
            continue
        plan_tool_alignment_trace_events += 1
        if bool(payload.get("blocked")):
            plan_tool_alignment_trace_blocked += 1
        if str(payload.get("event_type") or "").strip().lower() == "tool_alignment_rewrite":
            plan_tool_alignment_trace_rewrites += 1

    # Protocol fragility proxy from execution step parser/protocol metadata.
    protocol_turns = 0
    parse_failures = 0
    format_salvaged = 0
    protocol_fallbacks = 0
    truncation_detected = 0
    truncation_salvaged = 0
    semantic_complete = 0
    for e in execution_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        for s in steps:
            if not isinstance(s, dict):
                continue
            res = s.get("result") if isinstance(s.get("result"), dict) else {}
            meta = res.get("meta") if isinstance(res.get("meta"), dict) else {}
            if meta:
                protocol_turns += 1
                has_semantic_payload = bool(
                    (isinstance(res.get("call_tool"), dict) and str((res.get("call_tool") or {}).get("tool_name") or "").strip())
                    or (isinstance(res.get("tool_result"), dict) and str((res.get("tool_result") or {}).get("tool_name") or "").strip())
                )
                if str(res.get("status") or "").strip().lower() in {"ok", "success"} and has_semantic_payload:
                    semantic_complete += 1
            err = str(s.get("error") or res.get("error") or "").strip().lower()
            if "parse_failure" in err or "json_parse_error" in err:
                parse_failures += 1
            truncation_like = (
                "truncat" in err
                or "unexpected eof" in err
                or "unterminated" in err
                or "token limit" in err
            )
            if truncation_like:
                truncation_detected += 1
            if bool(meta.get("format_salvaged", False)):
                format_salvaged += 1
                if truncation_like:
                    truncation_salvaged += 1
            chain = meta.get("protocol_chain") if isinstance(meta.get("protocol_chain"), list) else []
            if len(chain) >= 2:
                protocol_fallbacks += 1
    protocol_failure_rate = (
        float(parse_failures) / float(protocol_turns)
        if protocol_turns > 0
        else 0.0
    )
    truncation_salvage_rate = (
        float(truncation_salvaged) / float(truncation_detected)
        if truncation_detected > 0
        else 1.0
    )
    parser_semantic_completeness = (
        float(semantic_complete) / float(protocol_turns)
        if protocol_turns > 0
        else 1.0
    )

    return {
        "perception_consistency": {
            "discovery_evidence_expected": discovery_evidence_expected,
            "discovery_evidence_found": discovery_evidence_found,
            "discovery_evidence_coverage": discovery_evidence_coverage,
            "examples_missing_evidence": discovery_evidence_examples,
        },
        "guessing_trap": {
            "planning_events": len(planning_events),
            "risky_plans": risky_plans,
            "risky_without_discovery": risky_without_discovery,
            "discovery_compliance_rate": compliance_rate,
            "examples": risky_examples,
        },
        "semantic_stagnation": {
            "weak_reasoning_detected": weak_reasoning_detected,
            "weak_reasoning_resolved": weak_reasoning_resolved,
            "weak_reasoning_fallback": weak_reasoning_fallback,
            "weak_resolution_rate": weak_resolution_rate,
        },
        "strategy_regression": {
            "repair_reused_previous_decomposition": strategy_regression_repairs,
            "fallback_decompositions": fallback_decompositions,
            "strategy_switching": {
                "planning_diag_total": planning_diag_total,
                "risky_without_diag": risky_without_diag,
                "variant_coverage": variant_coverage,
                "strategy_patch_coverage": patch_coverage,
                "retry_delta_coverage": retry_delta_coverage,
                "subcategory_alignment_rate": subtype_alignment,
                "attempt_band_required": attempt_band_required,
                "attempt_band_present": attempt_band_present,
                "attempt_band_coverage": attempt_band_coverage,
                "strategy_switch_effectiveness": strategy_switch_effectiveness,
                "legacy_diag_inferred": legacy_diag_inferred,
                "plan_execution_consistency_total": plan_exec_total,
                "plan_execution_expected_steps": plan_exec_expected_steps,
                "plan_execution_call_tool_coverage": plan_execution_call_tool_coverage,
                "plan_execution_tool_result_coverage": plan_execution_tool_result_coverage,
                "plan_execution_observed_coverage": plan_execution_observed_coverage,
                "plan_execution_consistency_rate": plan_execution_consistency_rate,
                "plan_execution_exact_match_total": plan_exec_exact_total,
                "plan_execution_exact_match_rate": plan_execution_exact_match_rate,
                "adaptive_alias_enabled": adaptive_alias_enabled,
                "adaptive_alias_entries": len(adaptive_alias_map),
                "adaptive_alias_applied": adaptive_alias_applied,
                "plan_tool_alignment_events": plan_tool_alignment_events,
                "plan_tool_alignment_blocked": plan_tool_alignment_blocked,
                "plan_tool_alignment_rewrites": plan_tool_alignment_rewrites,
                "plan_tool_alignment_trace_events": plan_tool_alignment_trace_events,
                "plan_tool_alignment_trace_blocked": plan_tool_alignment_trace_blocked,
                "plan_tool_alignment_trace_rewrites": plan_tool_alignment_trace_rewrites,
                "misalignment_eval_total": misalignment_eval_total,
                "misalignment_recovered_within_2": misalignment_recovered_within_2,
                "misalignment_recurred_within_2": misalignment_recurred_within_2,
                "misalignment_recovered_within_2_rate": misalignment_recovered_within_2_rate,
                "misalignment_recurrence_rate": misalignment_recurrence_rate,
                "plan_execution_consistency_examples": plan_exec_examples,
                "top_mismatch_patterns": [
                    {"pattern": k, "count": int(v)}
                    for k, v in mismatch_patterns.most_common(8)
                ],
                "examples": planning_diag_examples,
            },
            "execution_resilience": {
                "interrupt_total": interrupts_total,
                "hard_reset_total": hard_reset_total,
                "interrupt_effectiveness": interrupt_effectiveness,
                "reset_recovery_rate": reset_recovery_rate,
                "progress_sync_required": progress_sync_required,
                "progress_sync_compliant": progress_sync_compliant,
                "progress_sync_compliance": progress_sync_compliance,
                "cooldown_events": cooldown_events,
                "cooldown_mean": cooldown_mean,
                "cooldown_recurrence_rate": cooldown_recurrence_rate,
                "goal_reanchor_required": goal_reanchor_required,
                "goal_reanchor_success": goal_reanchor_success,
                "goal_reanchor_rate": goal_reanchor_rate,
                "plan_oscillation_events": plan_oscillation_events,
            },
        },
        "protocol_fragility": {
            "protocol_turns": protocol_turns,
            "parse_failures": parse_failures,
            "format_salvaged": format_salvaged,
            "protocol_fallbacks": protocol_fallbacks,
            "protocol_failure_rate": protocol_failure_rate,
            "truncation_detected": truncation_detected,
            "truncation_salvaged": truncation_salvaged,
            "truncation_salvage_rate": truncation_salvage_rate,
            "parser_semantic_completeness": parser_semantic_completeness,
        },
        "self_awareness_gap": {
            "blocked_action_unique": len(blocked_actions),
            "blocked_action_repeated": len(repeated_blocked),
            "top_repeated_actions": [
                {"action": k, "count": v}
                for k, v in sorted(repeated_blocked.items(), key=lambda x: (-x[1], x[0]))[:8]
            ],
        },
    }
