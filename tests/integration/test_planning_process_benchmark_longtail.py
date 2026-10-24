from __future__ import annotations

import json
from pathlib import Path

from scripts.planning_process_benchmark import run_benchmark


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _planning_row(
    *,
    trace_id: str,
    attempt_index: int,
    variant: str,
    subcategory: str,
    attempt_stage: str,
    attempt_band: str,
    strategy_patch_id: str,
    retry_reason: str,
    force_progress_sync: bool,
    include_diag: bool,
) -> dict:
    payload = {
        "attempt_index": attempt_index,
        "planner_repairs": ["inject_progress_sync_step"] if force_progress_sync else [],
        "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
    }
    if include_diag:
        payload["context_injected"] = {
            "planning_diagnostics": {
                "attempt_stage": attempt_stage,
                "attempt_band": attempt_band,
                "force_progress_sync": force_progress_sync,
                "payload_variant_id": variant,
                "error_subcategory": subcategory,
                "strategy_patch_id": strategy_patch_id,
                "retry_delta_reason": retry_reason,
            }
        }
    return {"trace_id": trace_id, "event_type": "planning", "payload": payload}


def _critic_rows(trace_id: str, *, interrupt_state: str, done: bool) -> list[dict]:
    rows = [{"trace_id": trace_id, "event_type": "critic", "payload": {"attempt_interrupt_state": interrupt_state}}]
    if done:
        rows.append({"trace_id": trace_id, "event_type": "critic", "payload": {"done": True}})
    return rows


def _build_longtail_events(*, degraded: bool) -> list[dict]:
    archetypes = [
        ("shell_timeout_batch_job", "pv_retry_shell_environment_timeout_error_shell_timeout_v1", "shell_timeout", "retry", "mid", "timeout_patch_v1", "retry_after=environment_timeout_error", "hard_reset"),
        ("shell_perm_repo", "pv_retry_shell_tool_execution_error_shell_permission_denied_v1", "shell_permission_denied", "retry", "mid", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("shell_cmd_not_found", "pv_retry_shell_tool_execution_error_shell_command_not_found_v1", "shell_command_not_found", "retry", "mid", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("shell_path_not_found", "pv_retry_shell_tool_execution_error_shell_path_not_found_v1", "shell_path_not_found", "retry", "mid", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("browser_nav_timeout", "pv_retry_browser_environment_timeout_error_browser_navigation_timeout_v1", "browser_navigation_timeout", "retry", "mid", "timeout_patch_v1", "retry_after=environment_timeout_error", "hard_reset"),
        ("browser_selector_missing", "pv_retry_browser_tool_execution_error_browser_selector_not_found_v1", "browser_selector_not_found", "retry", "mid", "browser_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("browser_stale_dom", "pv_retry_browser_tool_execution_error_browser_stale_element_v1", "browser_stale_element", "retry", "mid", "browser_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("browser_click_blocked", "pv_retry_browser_tool_execution_error_browser_click_intercepted_v1", "browser_click_intercepted", "retry", "mid", "browser_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("fs_perm_denied", "pv_retry_filesystem_tool_execution_error_filesystem_permission_denied_v1", "filesystem_permission_denied", "retry", "mid", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("fs_path_missing", "pv_retry_filesystem_tool_execution_error_filesystem_path_not_found_v1", "filesystem_path_not_found", "retry", "mid", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("json_parse_fail", "pv_retry_generic_model_syntax_error_na_v1", "json_parse_error", "retry", "mid", "syntax_patch_v1", "retry_after=model_syntax_error", "interrupt"),
        ("xml_truncated", "pv_retry_generic_model_syntax_error_na_v1", "xml_truncated", "retry", "mid", "syntax_patch_v1", "retry_after=model_syntax_error", "interrupt"),
        ("planner_loop_stuck", "pv_stuck_shell_logic_path_error_shell_timeout_v1", "shell_timeout", "stuck", "late", "logic_patch_v1", "retry_after=logic_path_error", "hard_reset"),
        ("planner_wrong_branch", "pv_stuck_browser_logic_path_error_browser_selector_not_found_v1", "browser_selector_not_found", "stuck", "late", "logic_patch_v1", "retry_after=logic_path_error", "hard_reset"),
        ("network_flaky", "pv_retry_shell_environment_timeout_error_shell_timeout_v1", "network_timeout", "retry", "mid", "timeout_patch_v1", "retry_after=environment_timeout_error", "interrupt"),
        ("api_rate_limited", "pv_retry_shell_tool_execution_error_shell_http_429_v1", "shell_http_429", "retry", "late", "rate_limit_patch_v1", "retry_after=tool_execution_error", "interrupt"),
        ("db_lock_conflict", "pv_retry_shell_tool_execution_error_shell_db_lock_v1", "shell_db_lock", "retry", "late", "tool_guardrails_v1", "retry_after=tool_execution_error", "interrupt"),
        ("cache_stale_state", "pv_retry_filesystem_logic_path_error_filesystem_stale_cache_v1", "filesystem_stale_cache", "stuck", "late", "logic_patch_v1", "retry_after=logic_path_error", "hard_reset"),
        ("multi_tool_deadlock", "pv_stuck_generic_system_error_na_v1", "tool_deadlock", "stuck", "late", "system_patch_v1", "retry_after=system_error", "hard_reset"),
        ("prompt_regression", "pv_retry_generic_logic_path_error_na_v1", "prompt_regression", "retry", "late", "logic_patch_v1", "retry_after=logic_path_error", "interrupt"),
    ]
    out: list[dict] = []
    for idx, (tid, variant, sub, stage, band, patch, retry_reason, interrupt_state) in enumerate(archetypes, start=1):
        include_diag = True
        force_progress_sync = (idx % 3 == 0)
        done = True
        if degraded:
            include_diag = idx % 2 == 0
            force_progress_sync = False
            done = idx % 4 == 0
        out.append(
            _planning_row(
                trace_id=tid,
                attempt_index=3 + (idx % 4),
                variant=variant,
                subcategory=sub,
                attempt_stage=stage,
                attempt_band=band,
                strategy_patch_id=patch if include_diag else "",
                retry_reason=retry_reason if include_diag else "",
                force_progress_sync=force_progress_sync,
                include_diag=include_diag,
            )
        )
        out.extend(_critic_rows(tid, interrupt_state=interrupt_state, done=done))
    return out


def test_planning_benchmark_longtail_replay_detects_regression(tmp_path: Path) -> None:
    traces = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    output_a = tmp_path / "generated" / "benchmarks" / "baseline.json"
    output_b = tmp_path / "generated" / "benchmarks" / "degraded.json"
    history = tmp_path / "generated" / "benchmarks" / "history.jsonl"
    _write_jsonl(traces, _build_longtail_events(degraded=False))
    _write_jsonl(audits, [])
    baseline = run_benchmark(
        repo_root=tmp_path,
        output=output_a,
        previous=None,
        min_score=0.55,
        history=history,
        domain_bucket="maintenance",
    )
    baseline_score = float(baseline.get("quality_score") or 0.0)
    assert baseline_score >= 0.70
    assert bool(baseline.get("pass")) is True

    _write_jsonl(traces, _build_longtail_events(degraded=True))
    degraded = run_benchmark(
        repo_root=tmp_path,
        output=output_b,
        previous=output_a,
        min_score=0.55,
        history=history,
        domain_bucket="maintenance",
    )
    degraded_score = float(degraded.get("quality_score") or 0.0)
    assert degraded_score < baseline_score
    assert (baseline_score - degraded_score) >= 0.20
    assert bool(degraded.get("improved_vs_previous")) is False
