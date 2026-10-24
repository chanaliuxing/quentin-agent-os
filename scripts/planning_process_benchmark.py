from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, float(x))))


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    if not str(raw or "").strip():
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not str(raw or "").strip():
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def compute_quality_score(audit: Dict[str, Any]) -> Dict[str, Any]:
    strategy = audit.get("strategy_regression") if isinstance(audit.get("strategy_regression"), dict) else {}
    switching = strategy.get("strategy_switching") if isinstance(strategy.get("strategy_switching"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}
    guessing = audit.get("guessing_trap") if isinstance(audit.get("guessing_trap"), dict) else {}

    strategy_switch_effectiveness = _safe_float(switching.get("strategy_switch_effectiveness"), 0.0)
    interrupt_effectiveness = _safe_float(resilience.get("interrupt_effectiveness"), 1.0)
    reset_recovery_rate = _safe_float(resilience.get("reset_recovery_rate"), 1.0)
    progress_sync_compliance = _safe_float(resilience.get("progress_sync_compliance"), 1.0)
    discovery_compliance_rate = _safe_float(guessing.get("discovery_compliance_rate"), 1.0)

    score = (
        (0.40 * strategy_switch_effectiveness)
        + (0.20 * interrupt_effectiveness)
        + (0.15 * reset_recovery_rate)
        + (0.15 * progress_sync_compliance)
        + (0.10 * discovery_compliance_rate)
    )

    return {
        "quality_score": float(max(0.0, min(1.0, score))),
        "components": {
            "strategy_switch_effectiveness": strategy_switch_effectiveness,
            "interrupt_effectiveness": interrupt_effectiveness,
            "reset_recovery_rate": reset_recovery_rate,
            "progress_sync_compliance": progress_sync_compliance,
            "discovery_compliance_rate": discovery_compliance_rate,
        },
    }


def compute_dimension_scores(audit: Dict[str, Any]) -> Dict[str, Any]:
    perception = audit.get("perception_consistency") if isinstance(audit.get("perception_consistency"), dict) else {}
    guessing = audit.get("guessing_trap") if isinstance(audit.get("guessing_trap"), dict) else {}
    strategy = audit.get("strategy_regression") if isinstance(audit.get("strategy_regression"), dict) else {}
    switching = strategy.get("strategy_switching") if isinstance(strategy.get("strategy_switching"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}
    protocol_fragility = audit.get("protocol_fragility") if isinstance(audit.get("protocol_fragility"), dict) else {}
    safety = audit.get("self_awareness_gap") if isinstance(audit.get("self_awareness_gap"), dict) else {}

    planning_events = int(guessing.get("planning_events") or 0)
    risky_plans = int(guessing.get("risky_plans") or 0)
    risky_without_discovery = int(guessing.get("risky_without_discovery") or 0)
    discovery_compliance_rate = _clamp01(_safe_float(guessing.get("discovery_compliance_rate"), 1.0))

    planning_diag_total = int(switching.get("planning_diag_total") or 0)
    legacy_diag_inferred = int(switching.get("legacy_diag_inferred") or 0)
    diag_coverage = _clamp01(float(planning_diag_total) / float(max(1, planning_events)))
    variant_coverage = _clamp01(_safe_float(switching.get("variant_coverage"), 0.0))
    patch_coverage = _clamp01(_safe_float(switching.get("strategy_patch_coverage"), 0.0))
    retry_delta_coverage = _clamp01(_safe_float(switching.get("retry_delta_coverage"), 0.0))
    subcategory_alignment_rate = _clamp01(_safe_float(switching.get("subcategory_alignment_rate"), 1.0))
    attempt_band_coverage = _clamp01(_safe_float(switching.get("attempt_band_coverage"), 1.0))
    strategy_switch_effectiveness = _clamp01(_safe_float(switching.get("strategy_switch_effectiveness"), 0.0))
    plan_execution_consistency_rate = _clamp01(_safe_float(switching.get("plan_execution_consistency_rate"), 1.0))
    plan_execution_exact_match_rate = _clamp01(_safe_float(switching.get("plan_execution_exact_match_rate"), 1.0))
    plan_execution_exact_match_total = int(switching.get("plan_execution_exact_match_total") or 0)
    plan_execution_expected_steps = int(switching.get("plan_execution_expected_steps") or 0)
    plan_execution_observed_coverage = _clamp01(
        _safe_float(switching.get("plan_execution_observed_coverage"), 1.0)
    )
    plan_execution_call_tool_coverage = _clamp01(
        _safe_float(switching.get("plan_execution_call_tool_coverage"), 1.0)
    )
    plan_tool_alignment_trace_events = int(switching.get("plan_tool_alignment_trace_events") or 0)
    plan_tool_alignment_trace_blocked = int(switching.get("plan_tool_alignment_trace_blocked") or 0)
    plan_tool_alignment_trace_rewrites = int(switching.get("plan_tool_alignment_trace_rewrites") or 0)
    misalignment_eval_total = int(switching.get("misalignment_eval_total") or 0)
    misalignment_recovered_within_2_rate = _clamp01(
        _safe_float(switching.get("misalignment_recovered_within_2_rate"), 1.0)
    )
    misalignment_recurrence_rate = _clamp01(
        _safe_float(switching.get("misalignment_recurrence_rate"), 0.0)
    )

    interrupt_effectiveness = _clamp01(_safe_float(resilience.get("interrupt_effectiveness"), 1.0))
    reset_recovery_rate = _clamp01(_safe_float(resilience.get("reset_recovery_rate"), 1.0))
    progress_sync_compliance = _clamp01(_safe_float(resilience.get("progress_sync_compliance"), 1.0))
    cooldown_recurrence_rate = _clamp01(_safe_float(resilience.get("cooldown_recurrence_rate"), 0.0))
    protocol_failure_rate = _clamp01(_safe_float(protocol_fragility.get("protocol_failure_rate"), 0.0))
    goal_reanchor_rate = _clamp01(_safe_float(resilience.get("goal_reanchor_rate"), 1.0))
    parser_semantic_completeness = _clamp01(_safe_float(protocol_fragility.get("parser_semantic_completeness"), 1.0))
    truncation_salvage_rate = _clamp01(_safe_float(protocol_fragility.get("truncation_salvage_rate"), 1.0))
    discovery_evidence_coverage = _clamp01(_safe_float(perception.get("discovery_evidence_coverage"), 1.0))

    blocked_action_repeated = int(safety.get("blocked_action_repeated") or 0)

    risky_without_diag_rate = 0.0
    try:
        risky_without_diag_rate = float(int(switching.get("risky_without_diag") or 0)) / float(max(1, risky_plans))
    except Exception:
        risky_without_diag_rate = 0.0

    score_discovery = _clamp01((0.70 * discovery_compliance_rate) + (0.30 * (1.0 - _clamp01(risky_without_diag_rate))))

    score_diagnostics = _clamp01(
        (0.15 * diag_coverage)
        + (0.20 * variant_coverage)
        + (0.20 * patch_coverage)
        + (0.15 * retry_delta_coverage)
        + (0.10 * subcategory_alignment_rate)
        + (0.20 * attempt_band_coverage)
    )

    score_switching = _clamp01(strategy_switch_effectiveness)

    score_resilience = _clamp01(
        (0.30 * interrupt_effectiveness)
        + (0.20 * reset_recovery_rate)
        + (0.30 * progress_sync_compliance)
        + (0.10 * (1.0 - cooldown_recurrence_rate))
        + (0.10 * goal_reanchor_rate)
    )

    score_safety = _clamp01(1.0 - min(0.60, 0.15 * float(max(0, blocked_action_repeated))))
    score_perception_consistency = _clamp01(discovery_evidence_coverage)
    score_protocol_robustness = _clamp01(
        (0.60 * (1.0 - protocol_failure_rate))
        + (0.20 * parser_semantic_completeness)
        + (0.20 * truncation_salvage_rate)
    )
    if plan_execution_exact_match_total > 0:
        score_planning_consistency = _clamp01(
            (0.50 * strategy_switch_effectiveness)
            + (0.30 * plan_execution_consistency_rate)
            + (0.15 * plan_execution_exact_match_rate)
            + (0.05 * misalignment_recovered_within_2_rate)
        )
    else:
        score_planning_consistency = _clamp01(
            (0.55 * strategy_switch_effectiveness)
            + (0.40 * plan_execution_consistency_rate)
            + (0.05 * misalignment_recovered_within_2_rate)
        )
    score_process_completeness = _clamp01(
        (0.30 * diag_coverage)
        + (0.30 * discovery_compliance_rate)
        + (0.25 * attempt_band_coverage)
        + (0.15 * plan_execution_observed_coverage)
    )
    score_dynamic_correction = score_resilience

    overall_v2 = _clamp01(
        (0.15 * score_discovery)
        + (0.20 * score_diagnostics)
        + (0.20 * score_switching)
        + (0.20 * score_resilience)
        + (0.10 * score_safety)
        + (0.10 * score_protocol_robustness)
        + (0.05 * score_perception_consistency)
    )

    capability_radar = {
        "perception_consistency": score_perception_consistency,
        "planning_consistency": score_planning_consistency,
        "dynamic_correction": score_dynamic_correction,
        "protocol_robustness": score_protocol_robustness,
        "process_completeness": score_process_completeness,
    }

    top_weaknesses = [
        {"name": k, "score": float(v)}
        for k, v in sorted(capability_radar.items(), key=lambda kv: (float(kv[1]), kv[0]))
    ]

    return {
        "overall_v2": overall_v2,
        "capability_radar": capability_radar,
        "top_weaknesses": top_weaknesses,
        "dimensions": {
            "perception_consistency": {
                "score": score_perception_consistency,
                "components": {
                    "discovery_evidence_coverage": discovery_evidence_coverage,
                },
            },
            "discovery_discipline": {
                "score": score_discovery,
                "components": {
                    "discovery_compliance_rate": discovery_compliance_rate,
                    "risky_without_diag_rate": _clamp01(risky_without_diag_rate),
                    "risky_plans": risky_plans,
                    "risky_without_discovery": risky_without_discovery,
                },
            },
            "planning_diagnostics": {
                "score": score_diagnostics,
                "components": {
                    "diag_coverage": diag_coverage,
                    "planning_events": planning_events,
                    "planning_diag_total": planning_diag_total,
                    "variant_coverage": variant_coverage,
                    "strategy_patch_coverage": patch_coverage,
                    "retry_delta_coverage": retry_delta_coverage,
                    "subcategory_alignment_rate": subcategory_alignment_rate,
                    "attempt_band_coverage": attempt_band_coverage,
                },
            },
            "strategy_switching": {
                "score": score_switching,
                "components": {
                    "strategy_switch_effectiveness": strategy_switch_effectiveness,
                    "plan_execution_consistency_rate": plan_execution_consistency_rate,
                    "plan_execution_exact_match_total": plan_execution_exact_match_total,
                    "plan_execution_exact_match_rate": plan_execution_exact_match_rate,
                    "plan_execution_expected_steps": plan_execution_expected_steps,
                    "plan_execution_observed_coverage": plan_execution_observed_coverage,
                    "plan_execution_call_tool_coverage": plan_execution_call_tool_coverage,
                    "plan_tool_alignment_trace_events": plan_tool_alignment_trace_events,
                    "plan_tool_alignment_trace_blocked": plan_tool_alignment_trace_blocked,
                    "plan_tool_alignment_trace_rewrites": plan_tool_alignment_trace_rewrites,
                    "misalignment_recovered_within_2_rate": misalignment_recovered_within_2_rate,
                    "misalignment_recurrence_rate": misalignment_recurrence_rate,
                    "adaptive_alias_entries": int(switching.get("adaptive_alias_entries") or 0),
                    "adaptive_alias_applied": int(switching.get("adaptive_alias_applied") or 0),
                },
            },
            "execution_resilience": {
                "score": score_resilience,
                "components": {
                    "interrupt_effectiveness": interrupt_effectiveness,
                    "reset_recovery_rate": reset_recovery_rate,
                    "progress_sync_compliance": progress_sync_compliance,
                    "cooldown_recurrence_rate": cooldown_recurrence_rate,
                    "goal_reanchor_rate": goal_reanchor_rate,
                },
            },
            "safety": {
                "score": score_safety,
                "components": {
                    "blocked_action_repeated": blocked_action_repeated,
                },
            },
            "protocol_robustness": {
                "score": score_protocol_robustness,
                "components": {
                    "protocol_failure_rate": protocol_failure_rate,
                    "parser_semantic_completeness": parser_semantic_completeness,
                    "truncation_salvage_rate": truncation_salvage_rate,
                },
            },
        },
    }


def analyze_benchmark_issues(audit: Dict[str, Any]) -> list[Dict[str, Any]]:
    perception = audit.get("perception_consistency") if isinstance(audit.get("perception_consistency"), dict) else {}
    guessing = audit.get("guessing_trap") if isinstance(audit.get("guessing_trap"), dict) else {}
    strategy = audit.get("strategy_regression") if isinstance(audit.get("strategy_regression"), dict) else {}
    switching = strategy.get("strategy_switching") if isinstance(strategy.get("strategy_switching"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}
    protocol_fragility = audit.get("protocol_fragility") if isinstance(audit.get("protocol_fragility"), dict) else {}
    safety = audit.get("self_awareness_gap") if isinstance(audit.get("self_awareness_gap"), dict) else {}

    planning_events = int(guessing.get("planning_events") or 0)
    risky_plans = int(guessing.get("risky_plans") or 0)
    risky_without_discovery = int(guessing.get("risky_without_discovery") or 0)
    discovery_compliance_rate = _clamp01(_safe_float(guessing.get("discovery_compliance_rate"), 1.0))

    planning_diag_total = int(switching.get("planning_diag_total") or 0)
    legacy_diag_inferred = int(switching.get("legacy_diag_inferred") or 0)
    diag_coverage = _clamp01(float(planning_diag_total) / float(max(1, planning_events)))
    subcategory_alignment_rate = _clamp01(_safe_float(switching.get("subcategory_alignment_rate"), 1.0))
    attempt_band_coverage = _clamp01(_safe_float(switching.get("attempt_band_coverage"), 1.0))
    strategy_switch_effectiveness = _clamp01(_safe_float(switching.get("strategy_switch_effectiveness"), 0.0))
    plan_execution_consistency_rate = _clamp01(_safe_float(switching.get("plan_execution_consistency_rate"), 1.0))
    plan_execution_exact_match_rate = _clamp01(_safe_float(switching.get("plan_execution_exact_match_rate"), 1.0))
    plan_execution_exact_match_total = int(switching.get("plan_execution_exact_match_total") or 0)
    plan_execution_expected_steps = int(switching.get("plan_execution_expected_steps") or 0)
    plan_execution_observed_coverage = _clamp01(
        _safe_float(switching.get("plan_execution_observed_coverage"), 1.0)
    )
    plan_execution_call_tool_coverage = _clamp01(
        _safe_float(switching.get("plan_execution_call_tool_coverage"), 1.0)
    )
    plan_tool_alignment_trace_events = int(switching.get("plan_tool_alignment_trace_events") or 0)
    plan_tool_alignment_trace_blocked = int(switching.get("plan_tool_alignment_trace_blocked") or 0)
    plan_tool_alignment_trace_rewrites = int(switching.get("plan_tool_alignment_trace_rewrites") or 0)
    misalignment_eval_total = int(switching.get("misalignment_eval_total") or 0)
    misalignment_recovered_within_2_rate = _clamp01(
        _safe_float(switching.get("misalignment_recovered_within_2_rate"), 1.0)
    )
    misalignment_recurrence_rate = _clamp01(
        _safe_float(switching.get("misalignment_recurrence_rate"), 0.0)
    )

    interrupt_effectiveness = _clamp01(_safe_float(resilience.get("interrupt_effectiveness"), 1.0))
    reset_recovery_rate = _clamp01(_safe_float(resilience.get("reset_recovery_rate"), 1.0))
    progress_sync_compliance = _clamp01(_safe_float(resilience.get("progress_sync_compliance"), 1.0))
    cooldown_recurrence_rate = _clamp01(_safe_float(resilience.get("cooldown_recurrence_rate"), 0.0))
    protocol_failure_rate = _clamp01(_safe_float(protocol_fragility.get("protocol_failure_rate"), 0.0))
    goal_reanchor_rate = _clamp01(_safe_float(resilience.get("goal_reanchor_rate"), 1.0))
    plan_oscillation_events = int(resilience.get("plan_oscillation_events") or 0)
    parser_semantic_completeness = _clamp01(_safe_float(protocol_fragility.get("parser_semantic_completeness"), 1.0))
    truncation_salvage_rate = _clamp01(_safe_float(protocol_fragility.get("truncation_salvage_rate"), 1.0))
    discovery_evidence_coverage = _clamp01(_safe_float(perception.get("discovery_evidence_coverage"), 1.0))

    blocked_action_repeated = int(safety.get("blocked_action_repeated") or 0)
    top_repeated_actions = safety.get("top_repeated_actions") if isinstance(safety.get("top_repeated_actions"), list) else []

    strategy_min = _env_float("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", 0.55)
    strategy_min_legacy = _env_float("QUENTIN_BENCH_PLANNING_STRATEGY_SWITCH_MIN_LEGACY", 0.25)
    interrupt_min = _env_float("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", 0.50)
    reset_min = _env_float("QUENTIN_VERIFY_RESET_RECOVERY_MIN", 0.40)
    progress_min = _env_float("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", 0.80)
    attempt_band_min = _env_float("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", 0.80)

    min_planning_events = _env_int("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", 20)
    discovery_min = _env_float("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", 0.85)
    diag_coverage_min = _env_float("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", 0.60)
    subcategory_alignment_min = _env_float("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", 0.65)
    cooldown_recurrence_max = _env_float("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", 0.35)
    blocked_repeated_max = _env_int("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", 0)
    discovery_evidence_min = _env_float("QUENTIN_BENCH_PLANNING_DISCOVERY_EVIDENCE_COVERAGE_MIN", 0.80)
    plan_exec_consistency_min = _env_float("QUENTIN_BENCH_PLANNING_PLAN_EXEC_CONSISTENCY_MIN", 0.45)
    plan_exec_min_samples = _env_int("QUENTIN_BENCH_PLANNING_PLAN_EXEC_MIN_SAMPLES", 20)
    plan_exec_exact_min = _env_float("QUENTIN_BENCH_PLANNING_PLAN_EXEC_EXACT_MATCH_MIN", 0.30)
    plan_exec_exact_min_samples = _env_int("QUENTIN_BENCH_PLANNING_PLAN_EXEC_EXACT_MIN_SAMPLES", 10)
    plan_exec_observed_coverage_min = _env_float("QUENTIN_BENCH_PLANNING_EXEC_OBSERVED_COVERAGE_MIN", 0.70)
    plan_exec_observed_min_samples = _env_int("QUENTIN_BENCH_PLANNING_EXEC_OBSERVED_MIN_SAMPLES", 20)
    misalignment_recovery_min = _env_float("QUENTIN_BENCH_PLANNING_MISALIGN_RECOVERY_MIN", 0.50)
    misalignment_recovery_min_samples = _env_int("QUENTIN_BENCH_PLANNING_MISALIGN_RECOVERY_MIN_SAMPLES", 6)
    misalignment_recurrence_max = _env_float("QUENTIN_BENCH_PLANNING_MISALIGN_RECURRENCE_MAX", 0.50)
    goal_reanchor_min = _env_float("QUENTIN_BENCH_PLANNING_GOAL_REANCHOR_MIN", 0.40)
    plan_oscillation_max = _env_int("QUENTIN_BENCH_PLANNING_OSCILLATION_MAX", 0)
    parser_semantic_min = _env_float("QUENTIN_BENCH_PLANNING_PARSER_SEMANTIC_MIN", 0.60)
    truncation_salvage_min = _env_float("QUENTIN_BENCH_PLANNING_TRUNCATION_SALVAGE_MIN", 0.50)
    alignment_trace_min_events = _env_int("QUENTIN_BENCH_PLANNING_ALIGNMENT_TRACE_MIN_EVENTS", 0)
    alignment_trace_min_planning_events = _env_int(
        "QUENTIN_BENCH_PLANNING_ALIGNMENT_TRACE_MIN_PLANNING_EVENTS",
        20,
    )
    protocol_failure_max = _env_float("QUENTIN_BENCH_PLANNING_PROTOCOL_FAILURE_MAX", 0.10)
    legacy_ratio = (
        float(legacy_diag_inferred) / float(max(1, planning_diag_total))
        if planning_diag_total > 0
        else 0.0
    )
    strategy_threshold_mode = "normal"
    if legacy_ratio >= 0.80:
        strategy_min = min(strategy_min, strategy_min_legacy)
        strategy_threshold_mode = "legacy_relaxed"

    issues: list[Dict[str, Any]] = []
    if planning_events < min_planning_events:
        issues.append(
            {
                "key": "insufficient_planning_samples",
                "severity": "warn",
                "value": planning_events,
                "threshold": min_planning_events,
                "details": {"planning_events": planning_events},
            }
        )
    if risky_plans > 0 and risky_without_discovery > 0:
        examples = guessing.get("examples") if isinstance(guessing.get("examples"), list) else []
        issues.append(
            {
                "key": "discovery_before_risky_violation",
                "severity": "fail",
                "value": risky_without_discovery,
                "threshold": 0,
                "details": {"risky_plans": risky_plans, "examples": examples[:5]},
            }
        )
    if discovery_compliance_rate < discovery_min:
        issues.append(
            {
                "key": "discovery_compliance_below_threshold",
                "severity": "fail",
                "value": discovery_compliance_rate,
                "threshold": discovery_min,
                "details": {"risky_plans": risky_plans, "risky_without_discovery": risky_without_discovery},
            }
        )
    if discovery_evidence_coverage < discovery_evidence_min:
        issues.append(
            {
                "key": "discovery_evidence_coverage_low",
                "severity": "warn" if discovery_evidence_coverage >= (discovery_evidence_min * 0.90) else "fail",
                "value": discovery_evidence_coverage,
                "threshold": discovery_evidence_min,
                "details": {
                    "expected": int(perception.get("discovery_evidence_expected") or 0),
                    "found": int(perception.get("discovery_evidence_found") or 0),
                    "examples": list(perception.get("examples_missing_evidence") or [])[:5],
                },
            }
        )
    if diag_coverage < diag_coverage_min:
        issues.append(
            {
                "key": "planning_diagnostics_coverage_low",
                "severity": "warn" if diag_coverage >= (diag_coverage_min * 0.80) else "fail",
                "value": diag_coverage,
                "threshold": diag_coverage_min,
                "details": {"planning_events": planning_events, "planning_diag_total": planning_diag_total},
            }
        )
    if subcategory_alignment_rate < subcategory_alignment_min:
        examples = switching.get("examples") if isinstance(switching.get("examples"), list) else []
        issues.append(
            {
                "key": "subcategory_alignment_low",
                "severity": "warn" if subcategory_alignment_rate >= (subcategory_alignment_min * 0.90) else "fail",
                "value": subcategory_alignment_rate,
                "threshold": subcategory_alignment_min,
                "details": {"examples": examples[:5]},
            }
        )
    if strategy_switch_effectiveness < strategy_min:
        issues.append(
            {
                "key": "strategy_switch_effectiveness_below_threshold",
                "severity": "fail",
                "value": strategy_switch_effectiveness,
                "threshold": strategy_min,
                "details": {
                    "threshold_mode": strategy_threshold_mode,
                    "legacy_diag_ratio": legacy_ratio,
                    "legacy_diag_inferred": legacy_diag_inferred,
                    "planning_diag_total": planning_diag_total,
                },
            }
        )
    plan_exec_total = int(switching.get("plan_execution_consistency_total") or 0)
    if plan_exec_total < plan_exec_min_samples:
        issues.append(
            {
                "key": "plan_execution_consistency_insufficient_samples",
                "severity": "warn",
                "value": plan_exec_total,
                "threshold": plan_exec_min_samples,
                "details": {},
            }
        )
    elif plan_execution_consistency_rate < plan_exec_consistency_min:
        issues.append(
            {
                "key": "plan_execution_consistency_low",
                "severity": "warn" if plan_execution_consistency_rate >= (plan_exec_consistency_min * 0.90) else "fail",
                "value": plan_execution_consistency_rate,
                "threshold": plan_exec_consistency_min,
                "details": {
                    "total": plan_exec_total,
                    "examples": list(switching.get("plan_execution_consistency_examples") or [])[:5],
                },
            }
        )
    if plan_execution_exact_match_total >= plan_exec_exact_min_samples and plan_execution_exact_match_rate < plan_exec_exact_min:
        issues.append(
            {
                "key": "plan_execution_exact_alignment_low",
                "severity": "warn" if plan_execution_exact_match_rate >= (plan_exec_exact_min * 0.90) else "fail",
                "value": plan_execution_exact_match_rate,
                "threshold": plan_exec_exact_min,
                "details": {
                    "total": plan_execution_exact_match_total,
                    "examples": list(switching.get("plan_execution_consistency_examples") or [])[:5],
                },
            }
        )
    if (
        plan_execution_expected_steps >= plan_exec_observed_min_samples
        and plan_execution_observed_coverage < plan_exec_observed_coverage_min
    ):
        issues.append(
            {
                "key": "plan_execution_observed_coverage_low",
                "severity": "warn" if plan_execution_observed_coverage >= (plan_exec_observed_coverage_min * 0.90) else "fail",
                "value": plan_execution_observed_coverage,
                "threshold": plan_exec_observed_coverage_min,
                "details": {
                    "expected_steps": plan_execution_expected_steps,
                    "call_tool_coverage": plan_execution_call_tool_coverage,
                },
            }
        )
    if (
        alignment_trace_min_events > 0
        and planning_diag_total >= alignment_trace_min_planning_events
        and plan_tool_alignment_trace_events < alignment_trace_min_events
    ):
        issues.append(
            {
                "key": "plan_tool_alignment_trace_missing",
                "severity": "warn",
                "value": plan_tool_alignment_trace_events,
                "threshold": alignment_trace_min_events,
                "details": {
                    "planning_diag_total": planning_diag_total,
                    "trace_blocked": plan_tool_alignment_trace_blocked,
                    "trace_rewrites": plan_tool_alignment_trace_rewrites,
                },
            }
        )
    if misalignment_eval_total >= misalignment_recovery_min_samples:
        if misalignment_recovered_within_2_rate < misalignment_recovery_min:
            issues.append(
                {
                    "key": "misalignment_recovery_slow",
                    "severity": "warn" if misalignment_recovered_within_2_rate >= (misalignment_recovery_min * 0.90) else "fail",
                    "value": misalignment_recovered_within_2_rate,
                    "threshold": misalignment_recovery_min,
                    "details": {"total": misalignment_eval_total},
                }
            )
        if misalignment_recurrence_rate > misalignment_recurrence_max:
            issues.append(
                {
                    "key": "misalignment_recurrence_high",
                    "severity": "warn" if misalignment_recurrence_rate <= (misalignment_recurrence_max * 1.20) else "fail",
                    "value": misalignment_recurrence_rate,
                    "threshold": misalignment_recurrence_max,
                    "details": {"total": misalignment_eval_total},
                }
            )
    if attempt_band_coverage < attempt_band_min:
        issues.append(
            {
                "key": "attempt_band_coverage_below_threshold",
                "severity": "warn" if attempt_band_coverage >= (attempt_band_min * 0.90) else "fail",
                "value": attempt_band_coverage,
                "threshold": attempt_band_min,
                "details": {
                    "attempt_band_required": int(switching.get("attempt_band_required") or 0),
                    "attempt_band_present": int(switching.get("attempt_band_present") or 0),
                },
            }
        )
    if interrupt_effectiveness < interrupt_min:
        issues.append(
            {
                "key": "interrupt_effectiveness_below_threshold",
                "severity": "warn" if interrupt_effectiveness >= (interrupt_min * 0.90) else "fail",
                "value": interrupt_effectiveness,
                "threshold": interrupt_min,
                "details": {
                    "interrupt_total": int(resilience.get("interrupt_total") or 0),
                },
            }
        )
    if reset_recovery_rate < reset_min:
        issues.append(
            {
                "key": "reset_recovery_rate_below_threshold",
                "severity": "warn" if reset_recovery_rate >= (reset_min * 0.90) else "fail",
                "value": reset_recovery_rate,
                "threshold": reset_min,
                "details": {
                    "hard_reset_total": int(resilience.get("hard_reset_total") or 0),
                },
            }
        )
    if goal_reanchor_rate < goal_reanchor_min and int(resilience.get("goal_reanchor_required") or 0) > 0:
        issues.append(
            {
                "key": "goal_reanchor_rate_low",
                "severity": "warn" if goal_reanchor_rate >= (goal_reanchor_min * 0.90) else "fail",
                "value": goal_reanchor_rate,
                "threshold": goal_reanchor_min,
                "details": {
                    "required": int(resilience.get("goal_reanchor_required") or 0),
                    "success": int(resilience.get("goal_reanchor_success") or 0),
                },
            }
        )
    if plan_oscillation_events > plan_oscillation_max:
        issues.append(
            {
                "key": "plan_oscillation_high",
                "severity": "warn" if plan_oscillation_events <= max(1, plan_oscillation_max + 1) else "fail",
                "value": plan_oscillation_events,
                "threshold": plan_oscillation_max,
                "details": {},
            }
        )
    if progress_sync_compliance < progress_min:
        issues.append(
            {
                "key": "progress_sync_compliance_below_threshold",
                "severity": "warn" if progress_sync_compliance >= (progress_min * 0.90) else "fail",
                "value": progress_sync_compliance,
                "threshold": progress_min,
                "details": {
                    "progress_sync_required": int(resilience.get("progress_sync_required") or 0),
                    "progress_sync_compliant": int(resilience.get("progress_sync_compliant") or 0),
                },
            }
        )
    if cooldown_recurrence_rate > cooldown_recurrence_max:
        issues.append(
            {
                "key": "cooldown_recurrence_high",
                "severity": "warn" if cooldown_recurrence_rate <= (cooldown_recurrence_max * 1.25) else "fail",
                "value": cooldown_recurrence_rate,
                "threshold": cooldown_recurrence_max,
                "details": {"cooldown_events": int(resilience.get("cooldown_events") or 0)},
            }
        )
    if blocked_action_repeated > blocked_repeated_max:
        issues.append(
            {
                "key": "blocked_action_recurrence",
                "severity": "warn" if blocked_action_repeated <= max(1, blocked_repeated_max + 1) else "fail",
                "value": blocked_action_repeated,
                "threshold": blocked_repeated_max,
                "details": {"top_repeated_actions": top_repeated_actions[:8]},
            }
        )
    if protocol_failure_rate > protocol_failure_max:
        issues.append(
            {
                "key": "protocol_failure_rate_high",
                "severity": "warn" if protocol_failure_rate <= (protocol_failure_max * 1.25) else "fail",
                "value": protocol_failure_rate,
                "threshold": protocol_failure_max,
                "details": {
                    "protocol_turns": int(protocol_fragility.get("protocol_turns") or 0),
                    "parse_failures": int(protocol_fragility.get("parse_failures") or 0),
                    "format_salvaged": int(protocol_fragility.get("format_salvaged") or 0),
                    "protocol_fallbacks": int(protocol_fragility.get("protocol_fallbacks") or 0),
                },
            }
        )
    if parser_semantic_completeness < parser_semantic_min:
        issues.append(
            {
                "key": "parser_semantic_completeness_low",
                "severity": "warn" if parser_semantic_completeness >= (parser_semantic_min * 0.90) else "fail",
                "value": parser_semantic_completeness,
                "threshold": parser_semantic_min,
                "details": {"protocol_turns": int(protocol_fragility.get("protocol_turns") or 0)},
            }
        )
    if int(protocol_fragility.get("truncation_detected") or 0) > 0 and truncation_salvage_rate < truncation_salvage_min:
        issues.append(
            {
                "key": "truncation_salvage_rate_low",
                "severity": "warn" if truncation_salvage_rate >= (truncation_salvage_min * 0.90) else "fail",
                "value": truncation_salvage_rate,
                "threshold": truncation_salvage_min,
                "details": {
                    "truncation_detected": int(protocol_fragility.get("truncation_detected") or 0),
                    "truncation_salvaged": int(protocol_fragility.get("truncation_salvaged") or 0),
                },
            }
        )
    mismatch_patterns = switching.get("top_mismatch_patterns") if isinstance(switching.get("top_mismatch_patterns"), list) else []
    if mismatch_patterns:
        top_pattern = mismatch_patterns[0] if isinstance(mismatch_patterns[0], dict) else {}
        top_count = int(top_pattern.get("count") or 0)
        if top_count >= 3:
            issues.append(
                {
                    "key": "top_mismatch_pattern_repeated",
                    "severity": "warn",
                    "value": top_count,
                    "threshold": 2,
                    "details": {"pattern": str(top_pattern.get("pattern") or "")},
                }
            )

    sev_rank = {"fail": 0, "warn": 1, "info": 2}

    def sort_key(i: Dict[str, Any]) -> tuple:
        sev = str(i.get("severity") or "warn")
        return (sev_rank.get(sev, 9), str(i.get("key") or ""))

    issues.sort(key=sort_key)
    return issues


def load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_history(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except Exception:
        return []
    return rows


def _domain_breakdown(rows: list[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows + [current]:
        cal = r.get("calibration_bucket") if isinstance(r.get("calibration_bucket"), dict) else {}
        dom = str(cal.get("domain") or "global").strip().lower() or "global"
        b = buckets.setdefault(
            dom,
            {
                "runs": 0,
                "avg_quality_score": 0.0,
                "fail_issues": 0,
                "warn_issues": 0,
            },
        )
        b["runs"] += 1
        b["avg_quality_score"] += float(r.get("quality_score") or 0.0)
        issues = r.get("issues") if isinstance(r.get("issues"), list) else []
        for it in issues:
            if not isinstance(it, dict):
                continue
            sev = str(it.get("severity") or "").strip().lower()
            if sev == "fail":
                b["fail_issues"] += 1
            elif sev == "warn":
                b["warn_issues"] += 1
    for b in buckets.values():
        runs = int(b.get("runs") or 0)
        if runs > 0:
            b["avg_quality_score"] = float(b.get("avg_quality_score") or 0.0) / float(runs)
    return buckets


def run_benchmark(
    *,
    repo_root: Path,
    output: Path,
    previous: Path | None = None,
    min_score: float = 0.55,
    history: Path | None = None,
    domain_bucket: str = "global",
) -> Dict[str, Any]:
    adaptive_ab_mode = str(os.getenv("QUENTIN_BENCH_ADAPTIVE_ALIAS_AB", "")).strip().lower() in {"1", "true", "yes", "on"}
    audit = build_intelligence_audit(repo_root=repo_root, adaptive_alias=True if adaptive_ab_mode else None)
    score_obj = compute_quality_score(audit)
    dimension_obj = compute_dimension_scores(audit)
    issues = analyze_benchmark_issues(audit)
    ab_comparison: Dict[str, Any] = {}
    if adaptive_ab_mode:
        static_audit = build_intelligence_audit(repo_root=repo_root, adaptive_alias=False)
        adaptive_audit = build_intelligence_audit(repo_root=repo_root, adaptive_alias=True)
        static_dim = compute_dimension_scores(static_audit)
        adaptive_dim = compute_dimension_scores(adaptive_audit)
        static_sw = ((static_audit.get("strategy_regression") or {}).get("strategy_switching") or {})
        adaptive_sw = ((adaptive_audit.get("strategy_regression") or {}).get("strategy_switching") or {})
        ab_comparison = {
            "enabled": True,
            "exact_match_rate_static": float(static_sw.get("plan_execution_exact_match_rate") or 0.0),
            "exact_match_rate_adaptive": float(adaptive_sw.get("plan_execution_exact_match_rate") or 0.0),
            "quality_score_v2_static": float(static_dim.get("overall_v2") or 0.0),
            "quality_score_v2_adaptive": float(adaptive_dim.get("overall_v2") or 0.0),
        }

    prev_score = None
    prev_report = load_report(previous) if previous is not None else {}
    if prev_report:
        try:
            prev_score = float(prev_report.get("quality_score"))
        except Exception:
            prev_score = None

    quality_score = float(score_obj.get("quality_score") or 0.0)
    improved_vs_previous = True if prev_score is None else (quality_score >= prev_score)
    pass_gate = quality_score >= float(min_score)

    report: Dict[str, Any] = {
        "generated_at": _now_utc_iso(),
        "repo_root": str(repo_root.resolve()),
        "calibration_bucket": {"domain": str(domain_bucket or "global").strip().lower() or "global"},
        "quality_score": quality_score,
        "quality_score_v2": float(dimension_obj.get("overall_v2") or 0.0),
        "capability_radar": dimension_obj.get("capability_radar", {}),
        "top_weaknesses": dimension_obj.get("top_weaknesses", []),
        "min_score": float(min_score),
        "pass": pass_gate,
        "improved_vs_previous": improved_vs_previous,
        "previous_score": prev_score,
        "score_components": score_obj.get("components", {}),
        "dimension_scores": dimension_obj.get("dimensions", {}),
        "issues": issues,
        "intelligence_audit": audit,
    }
    if ab_comparison:
        report["adaptive_alias_ab"] = ab_comparison
    if history is not None:
        rows = _load_history(history)
        report["domain_breakdown"] = _domain_breakdown(rows, report)
    else:
        report["domain_breakdown"] = _domain_breakdown([], report)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if history is not None:
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Planning process benchmark report generator")
    p.add_argument("--repo-root", default=".", help="Repository root")
    p.add_argument("--output", default="generated/benchmarks/planning_process_benchmark_report.json", help="Output report path")
    p.add_argument("--previous", default="generated/benchmarks/planning_process_benchmark_prev.json", help="Previous report path")
    p.add_argument("--history", default="generated/benchmarks/planning_process_benchmark_history.jsonl", help="History jsonl path")
    p.add_argument("--domain-bucket", default="global", help="Calibration domain bucket label (e.g. maintenance/research/global)")
    p.add_argument("--min-score", type=float, default=0.55, help="Minimum quality score threshold")
    args = p.parse_args()

    report = run_benchmark(
        repo_root=Path(args.repo_root),
        output=Path(args.output),
        previous=Path(args.previous) if args.previous else None,
        min_score=float(args.min_score),
        history=Path(args.history) if args.history else None,
        domain_bucket=str(args.domain_bucket or "global"),
    )
    audit = report.get("intelligence_audit") if isinstance(report.get("intelligence_audit"), dict) else {}
    guessing = audit.get("guessing_trap") if isinstance(audit.get("guessing_trap"), dict) else {}
    print(
        json.dumps(
            {
                "quality_score": report.get("quality_score"),
                "quality_score_v2": report.get("quality_score_v2"),
                "min_score": report.get("min_score"),
                "pass": report.get("pass"),
                "improved_vs_previous": report.get("improved_vs_previous"),
                "previous_score": report.get("previous_score"),
                "planning_events": int(guessing.get("planning_events") or 0),
                "top_issue_keys": [str(x.get("key") or "") for x in (report.get("issues") or [])[:6]],
            },
            ensure_ascii=False,
        )
    )
    return 0 if bool(report.get("pass")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
