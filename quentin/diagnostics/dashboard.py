from __future__ import annotations

from dataclasses import dataclass, asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class DashboardSnapshot:
    """
    系统状态快照，用于“仪表盘”展示。
    """
    timestamp: str
    blueprint_summary: Dict[str, Any]
    immune_summary: Dict[str, Any]
    patch_summary: Dict[str, Any]
    intelligence_summary: Dict[str, Any]
    intelligence_audit_summary: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    notes: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntelligenceAlertThresholds:
    planner_repair_rate_warn: float = 0.35
    blocked_repeat_ratio_warn: float = 0.25
    done_weak_resolution_rate_warn: float = 0.5
    discovery_precheck_compliance_warn: float = 0.8
    blocked_action_repeated_warn: int = 1
    strategy_fallback_decompositions_warn: int = 1
    intelligence_recovery_success_rate_warn: float = 0.6
    intelligence_recovery_min_samples_warn: int = 4
    intelligence_recovery_trend_drop_warn: float = 0.2
    intelligence_recovery_focus_success_rate_warn: float = 0.5
    intelligence_recovery_focus_min_samples_warn: int = 3


def _get_patch_status(obj: Any) -> Optional[str]:
    """
    兼容：
    - PatchTestReport dataclass
    - dict（from to_dict()）
    - 其它含 status 属性的对象
    """
    if isinstance(obj, dict):
        return obj.get("status")
    if is_dataclass(obj):
        return getattr(obj, "status", None)
    return getattr(obj, "status", None)


def build_dashboard_snapshot(
    *,
    blueprint_report: Optional[Dict[str, Any]],
    immune_result: Optional[Dict[str, Any]],
    patch_reports: List[Any],
    intelligence_report: Optional[Dict[str, Any]] = None,
    intelligence_audit_report: Optional[Dict[str, Any]] = None,
    thresholds: Optional[IntelligenceAlertThresholds] = None,
    notes: Optional[Dict[str, Any]] = None,
) -> DashboardSnapshot:
    """
    根据当前一轮的蓝皮书报告 / 免疫结果 / patch 测试结果，构造 DashboardSnapshot。
    """
    ts = now_iso()

    # 1) 蓝皮书部分
    if blueprint_report is None:
        bp_summary = {
            "gap_count": 0,
            "missing_files": 0,
            "stub_implementations": 0,
            "spec_version": "unknown",
        }
    else:
        summary = blueprint_report.get("summary") or {}
        bp_summary = {
            "gap_count": summary.get("gap_count", 0),
            "missing_files": summary.get("missing_files", 0),
            "stub_implementations": summary.get("stub_implementations", 0),
            "spec_version": blueprint_report.get("spec_version", "unknown"),
        }

    # 2) 免疫循环部分
    if immune_result is None:
        im_summary = {
            "cases_in_last_scan": 0,
        }
    else:
        im_summary = {
            "cases_in_last_scan": immune_result.get("count", 0),
        }

    # 3) patch 测试部分
    num_patches = len(patch_reports)
    num_passed = sum(1 for r in patch_reports if _get_patch_status(r) == "passed")
    num_failed = sum(1 for r in patch_reports if _get_patch_status(r) == "failed")
    num_error = sum(1 for r in patch_reports if _get_patch_status(r) == "error")

    patch_summary = {
        "num_patches": num_patches,
        "num_passed": num_passed,
        "num_failed": num_failed,
        "num_error": num_error,
    }

    thr = thresholds or IntelligenceAlertThresholds()
    intel = intelligence_report or {}
    planner = intel.get("planner_repairs") if isinstance(intel.get("planner_repairs"), dict) else {}
    blocked = intel.get("blocked_action_recurrence") if isinstance(intel.get("blocked_action_recurrence"), dict) else {}
    done_q = intel.get("done_council_quality") if isinstance(intel.get("done_council_quality"), dict) else {}
    recovery_loop = intel.get("recovery_loop") if isinstance(intel.get("recovery_loop"), dict) else {}
    focus_rows = recovery_loop.get("focus_breakdown") if isinstance(recovery_loop.get("focus_breakdown"), list) else []

    intelligence_summary = {
        "planner_repair_rate": float(planner.get("repair_rate") or 0.0),
        "discovery_precheck_compliance_rate": float(
            (
                (planner.get("discovery_precheck") or {}).get("compliance_rate")
                if isinstance(planner.get("discovery_precheck"), dict)
                else 1.0
            )
            or 0.0
        ),
        "blocked_repeat_ratio": float(blocked.get("repeat_ratio") or 0.0),
        "done_weak_resolution_rate": (
            None if done_q.get("weak_resolution_rate") is None else float(done_q.get("weak_resolution_rate"))
        ),
        "intelligence_recovery_success_rate": float(recovery_loop.get("success_rate") or 0.0),
        "intelligence_recovery_sample_size": int(recovery_loop.get("sample_size") or 0),
        "intelligence_recovery_recent_window_rate": (
            None if recovery_loop.get("recent_window_rate") is None else float(recovery_loop.get("recent_window_rate"))
        ),
        "intelligence_recovery_prior_window_rate": (
            None if recovery_loop.get("prior_window_rate") is None else float(recovery_loop.get("prior_window_rate"))
        ),
        "intelligence_recovery_trend_delta": (
            None if recovery_loop.get("trend_delta") is None else float(recovery_loop.get("trend_delta"))
        ),
        "intelligence_recovery_trend_window_size": int(recovery_loop.get("trend_window_size") or 0),
        "intelligence_recovery_focus_breakdown": focus_rows,
        "planner_repair_reasons": planner.get("repair_reason_counts") or {},
        "blocked_top_actions": blocked.get("top_actions") or [],
    }
    audit = intelligence_audit_report or {}
    guessing = audit.get("guessing_trap") if isinstance(audit.get("guessing_trap"), dict) else {}
    semantic = audit.get("semantic_stagnation") if isinstance(audit.get("semantic_stagnation"), dict) else {}
    strategy = audit.get("strategy_regression") if isinstance(audit.get("strategy_regression"), dict) else {}
    self_awareness = audit.get("self_awareness_gap") if isinstance(audit.get("self_awareness_gap"), dict) else {}
    intelligence_audit_summary = {
        "guessing_risky_without_discovery": int(guessing.get("risky_without_discovery") or 0),
        "guessing_discovery_compliance_rate": float(guessing.get("discovery_compliance_rate") or 1.0),
        "semantic_weak_reasoning_detected": int(semantic.get("weak_reasoning_detected") or 0),
        "semantic_weak_resolution_rate": (
            None if semantic.get("weak_resolution_rate") is None else float(semantic.get("weak_resolution_rate"))
        ),
        "strategy_fallback_decompositions": int(strategy.get("fallback_decompositions") or 0),
        "self_awareness_blocked_action_repeated": int(self_awareness.get("blocked_action_repeated") or 0),
        "self_awareness_top_repeated_actions": self_awareness.get("top_repeated_actions") or [],
    }

    alerts: List[Dict[str, Any]] = []
    if intelligence_summary["planner_repair_rate"] >= float(thr.planner_repair_rate_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "planner_repair_rate_high",
                "message": (
                    f"Planner repair rate is high ({intelligence_summary['planner_repair_rate']:.2f} >= "
                    f"{thr.planner_repair_rate_warn:.2f})."
                ),
            }
        )
    if intelligence_summary["blocked_repeat_ratio"] >= float(thr.blocked_repeat_ratio_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "blocked_action_repeat_high",
                "message": (
                    f"Blocked action recurrence is high ({intelligence_summary['blocked_repeat_ratio']:.2f} >= "
                    f"{thr.blocked_repeat_ratio_warn:.2f})."
                ),
            }
        )
    if intelligence_summary["discovery_precheck_compliance_rate"] < float(thr.discovery_precheck_compliance_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "discovery_precheck_compliance_low",
                "message": (
                    f"Discovery precheck compliance is low ({intelligence_summary['discovery_precheck_compliance_rate']:.2f} < "
                    f"{thr.discovery_precheck_compliance_warn:.2f})."
                ),
            }
        )
    weak_resolution_rate = intelligence_summary["done_weak_resolution_rate"]
    if weak_resolution_rate is not None and weak_resolution_rate < float(thr.done_weak_resolution_rate_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "done_weak_resolution_low",
                "message": (
                    f"Done-council weak reasoning resolution is low ({weak_resolution_rate:.2f} < "
                    f"{thr.done_weak_resolution_rate_warn:.2f})."
                ),
            }
        )
    if (
        int(intelligence_summary["intelligence_recovery_sample_size"] or 0) >= int(thr.intelligence_recovery_min_samples_warn)
        and float(intelligence_summary["intelligence_recovery_success_rate"] or 0.0)
        < float(thr.intelligence_recovery_success_rate_warn)
    ):
        alerts.append(
            {
                "severity": "warning",
                "code": "intelligence_recovery_success_low",
                "message": (
                    f"Intelligence recovery success rate is low "
                    f"({float(intelligence_summary['intelligence_recovery_success_rate']):.2f} < "
                    f"{float(thr.intelligence_recovery_success_rate_warn):.2f}) with sample size "
                    f"{int(intelligence_summary['intelligence_recovery_sample_size'])}."
                ),
            }
        )
    trend_delta = intelligence_summary["intelligence_recovery_trend_delta"]
    trend_window = int(intelligence_summary["intelligence_recovery_trend_window_size"] or 0)
    if (
        trend_delta is not None
        and trend_window >= 2
        and float(trend_delta) <= -float(thr.intelligence_recovery_trend_drop_warn)
    ):
        alerts.append(
            {
                "severity": "warning",
                "code": "intelligence_recovery_trend_down",
                "message": (
                    f"Intelligence recovery trend is worsening "
                    f"(delta {float(trend_delta):.2f} <= -{float(thr.intelligence_recovery_trend_drop_warn):.2f}, "
                    f"window={trend_window})."
                ),
            }
        )
    weak_focuses: List[Dict[str, Any]] = []
    for row in focus_rows:
        if not isinstance(row, dict):
            continue
        total = int(row.get("total") or 0)
        done = int(row.get("done") or 0)
        failed = int(row.get("failed") or 0)
        settled = done + failed
        if settled < int(thr.intelligence_recovery_focus_min_samples_warn):
            continue
        rate = row.get("success_rate")
        if rate is None:
            continue
        try:
            r = float(rate)
        except Exception:
            continue
        if r < float(thr.intelligence_recovery_focus_success_rate_warn):
            weak_focuses.append(
                {
                    "focus": str(row.get("focus") or "unknown"),
                    "success_rate": r,
                    "total": total,
                    "settled": settled,
                    "failed": failed,
                }
            )
    if weak_focuses:
        worst = sorted(weak_focuses, key=lambda x: (x["success_rate"], -x["settled"], x["focus"]))[0]
        alerts.append(
            {
                "severity": "warning",
                "code": "intelligence_recovery_focus_low",
                "message": (
                    f"Recovery focus '{worst['focus']}' has low success rate "
                    f"({worst['success_rate']:.2f} < {float(thr.intelligence_recovery_focus_success_rate_warn):.2f}, "
                    f"settled={int(worst['settled'])})."
                ),
                "context": {"weak_focuses": weak_focuses[:5]},
            }
        )
    if intelligence_audit_summary["guessing_risky_without_discovery"] > 0:
        alerts.append(
            {
                "severity": "warning",
                "code": "guessing_trap_detected",
                "message": (
                    f"Risky plans without discovery precheck detected "
                    f"({intelligence_audit_summary['guessing_risky_without_discovery']})."
                ),
            }
        )
    if intelligence_audit_summary["strategy_fallback_decompositions"] >= int(thr.strategy_fallback_decompositions_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "strategy_regression_detected",
                "message": (
                    f"Fallback decompositions detected "
                    f"({intelligence_audit_summary['strategy_fallback_decompositions']} >= "
                    f"{int(thr.strategy_fallback_decompositions_warn)})."
                ),
            }
        )
    if intelligence_audit_summary["self_awareness_blocked_action_repeated"] >= int(thr.blocked_action_repeated_warn):
        alerts.append(
            {
                "severity": "warning",
                "code": "blocked_action_repeated_detected",
                "message": (
                    f"Repeated blocked actions detected "
                    f"({intelligence_audit_summary['self_awareness_blocked_action_repeated']} >= "
                    f"{int(thr.blocked_action_repeated_warn)})."
                ),
            }
        )

    snapshot = DashboardSnapshot(
        timestamp=ts,
        blueprint_summary=bp_summary,
        immune_summary=im_summary,
        patch_summary=patch_summary,
        intelligence_summary=intelligence_summary,
        intelligence_audit_summary=intelligence_audit_summary,
        alerts=alerts,
        notes=notes or {},
    )
    return snapshot


def write_dashboard_snapshot(
    *,
    repo_root: str | Path,
    snapshot: DashboardSnapshot,
    filename: str = "data/dashboard/latest_snapshot.json",
) -> Path:
    """
    把 DashboardSnapshot 写成 JSON 文件。

    默认路径：<repo_root>/data/dashboard/latest_snapshot.json
    """
    repo_root = Path(repo_root).resolve()
    out_path = repo_root / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2)
    out_path.write_text(text, encoding="utf-8")

    logger.info("Dashboard snapshot written to %s", out_path)
    return out_path
