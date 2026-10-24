from __future__ import annotations

import json
from pathlib import Path

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_planning_process_benchmark_archetypes(tmp_path: Path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    _write_rows(
        events,
        [
            {
                "trace_id": "timeout-1",
                "event_type": "planning",
                "payload": {
                    "planner_repairs": ["inject_progress_sync_step"],
                    "context_injected": {
                        "planning_diagnostics": {
                            "attempt_stage": "stuck",
                            "force_progress_sync": True,
                            "payload_variant_id": "pv_retry_shell_environment_timeout_error_shell_timeout_v1",
                            "error_subcategory": "shell_timeout",
                            "strategy_patch_id": "environment_timeout_patch_v1",
                            "retry_delta_reason": "retry_after=environment_timeout_error",
                        }
                    },
                    "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                },
            },
            {
                "trace_id": "timeout-1",
                "event_type": "critic",
                "payload": {"attempt_interrupt_state": "hard_reset"},
            },
            {
                "trace_id": "timeout-1",
                "event_type": "critic",
                "payload": {"done": True},
            },
        ],
    )
    _write_rows(audits, [])

    report = build_intelligence_audit(repo_root=tmp_path)
    strategy = report.get("strategy_regression") if isinstance(report.get("strategy_regression"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}
    assert float(resilience.get("interrupt_effectiveness") or 0.0) >= 1.0
    assert float(resilience.get("reset_recovery_rate") or 0.0) >= 1.0
    assert float(resilience.get("progress_sync_compliance") or 0.0) >= 1.0


def test_planning_process_benchmark_multi_archetype_replay(tmp_path: Path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    planning_rows: list[dict] = []
    critic_rows: list[dict] = []
    archetypes = [
        ("timeout-shell", "pv_retry_shell_environment_timeout_error_shell_timeout_v1", "shell_timeout"),
        ("permission-shell", "pv_retry_shell_tool_execution_error_shell_permission_denied_v1", "shell_permission_denied"),
        ("cmd-not-found", "pv_retry_shell_tool_execution_error_shell_command_not_found_v1", "shell_command_not_found"),
        ("browser-timeout", "pv_retry_browser_environment_timeout_error_browser_navigation_timeout_v1", "browser_navigation_timeout"),
        ("browser-selector", "pv_retry_browser_tool_execution_error_browser_selector_not_found_v1", "browser_selector_not_found"),
        ("browser-stale", "pv_retry_browser_tool_execution_error_browser_stale_element_v1", "browser_stale_element"),
        ("fs-path", "pv_retry_filesystem_tool_execution_error_filesystem_path_not_found_v1", "filesystem_path_not_found"),
        ("fs-perm", "pv_retry_filesystem_tool_execution_error_filesystem_permission_denied_v1", "filesystem_permission_denied"),
        ("xml-trunc", "pv_retry_generic_model_syntax_error_na_v1", ""),
        ("loop-recovery", "pv_stuck_shell_logic_path_error_shell_timeout_v1", "shell_timeout"),
    ]
    for idx, (tid, variant, sub) in enumerate(archetypes, start=1):
        planning_rows.append(
            {
                "trace_id": tid,
                "event_type": "planning",
                "payload": {
                    "attempt_index": 3 + (idx % 3),
                    "planner_repairs": ["inject_progress_sync_step"] if idx % 2 == 0 else [],
                    "context_injected": {
                        "planning_diagnostics": {
                            "attempt_stage": "retry" if idx % 2 else "stuck",
                            "attempt_band": "mid" if idx < 8 else "late",
                            "force_progress_sync": bool(idx % 2 == 0),
                            "payload_variant_id": variant,
                            "error_subcategory": sub,
                            "strategy_patch_id": "strategy_patch_v1",
                            "retry_delta_reason": "retry_after=tool_execution_error",
                        }
                    },
                    "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                },
            }
        )
        critic_rows.append(
            {
                "trace_id": tid,
                "event_type": "critic",
                "payload": {"attempt_interrupt_state": "interrupt" if idx % 2 else "hard_reset"},
            }
        )
        critic_rows.append(
            {
                "trace_id": tid,
                "event_type": "critic",
                "payload": {"done": True},
            }
        )
    _write_rows(events, planning_rows + critic_rows)
    _write_rows(audits, [])

    report = build_intelligence_audit(repo_root=tmp_path)
    strategy = report.get("strategy_regression") if isinstance(report.get("strategy_regression"), dict) else {}
    switching = strategy.get("strategy_switching") if isinstance(strategy.get("strategy_switching"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}
    assert int(switching.get("planning_diag_total") or 0) >= 10
    assert float(switching.get("attempt_band_coverage") or 0.0) >= 0.9
    assert float(resilience.get("interrupt_effectiveness") or 0.0) >= 0.9
    assert "cooldown_mean" in resilience
