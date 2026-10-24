# meta_agent/immune/detector.py
from __future__ import annotations
from typing import List
from datetime import datetime
import uuid

from meta_agent.monitoring.status_snapshot import StatusSnapshot
from meta_agent.immune.models import (
    ImmuneCase,
    ImmuneCaseKind,
    ImmuneCaseSeverity,
)


def _new_case(
    kind: ImmuneCaseKind,
    severity: ImmuneCaseSeverity,
    summary: str,
    details: dict,
) -> ImmuneCase:
    return ImmuneCase(
        id=str(uuid.uuid4()),
        kind=kind,
        severity=severity,
        summary=summary,
        details=details,
    )


def detect_cases_from_snapshot(snapshot: StatusSnapshot) -> List[ImmuneCase]:
    """
    v1: 用一些朴素阈值规则，基于最近 window_hours 的状态做“体检”，
    生成若干 ImmuneCase。
    """
    cases: List[ImmuneCase] = []

    # 1) 整体错误率激增
    ts = snapshot.task_stats_overall
    if ts.total >= 20 and ts.fail_rate > 0.3:
        cases.append(
            _new_case(
                kind=ImmuneCaseKind.ERROR_SPIKE,
                severity=ImmuneCaseSeverity.CRITICAL,
                summary=f"Overall task fail_rate={ts.fail_rate:.2f} (>0.30) over last {snapshot.window_hours}h.",
                details={
                    "window_hours": snapshot.window_hours,
                    "total_tasks": ts.total,
                    "success_rate": ts.success_rate,
                    "fail_rate": ts.fail_rate,
                },
            )
        )

    # 2) 某个 domain 的失败率异常
    for domain, dts in snapshot.task_stats_by_domain.items():
        if dts.total < 10:
            continue
        if dts.fail_rate > 0.4:
            severity = (
                ImmuneCaseSeverity.CRITICAL
                if dts.fail_rate > 0.6
                else ImmuneCaseSeverity.HIGH
            )
            cases.append(
                _new_case(
                    kind=ImmuneCaseKind.DOMAIN_REGRESSION,
                    severity=severity,
                    summary=(
                        f"Domain '{domain}' fail_rate={dts.fail_rate:.2f} (>0.40) "
                        f"over last {snapshot.window_hours}h."
                    ),
                    details={
                        "domain": domain,
                        "total_tasks": dts.total,
                        "success_rate": dts.success_rate,
                        "fail_rate": dts.fail_rate,
                    },
                )
            )

    # 3) Patch 评估：失败风暴
    ps = snapshot.patches
    if ps.total_evaluated >= 5:
        fail_ratio = ps.fail_count / ps.total_evaluated if ps.total_evaluated else 0.0
        if fail_ratio > 0.6:
            cases.append(
                _new_case(
                    kind=ImmuneCaseKind.PATCH_FAILURE_STORM,
                    severity=ImmuneCaseSeverity.HIGH,
                    summary=(
                        f"Patch failure storm: {ps.fail_count}/{ps.total_evaluated} "
                        f"patches failed evaluation in last {snapshot.window_hours}h."
                    ),
                    details={
                        "total_evaluated": ps.total_evaluated,
                        "fail_count": ps.fail_count,
                        "pass_count": ps.pass_count,
                        "needs_review": ps.needs_review_count,
                    },
                )
            )

    # 4) 实验不稳定：实验很多但 patch 通过很少
    es = snapshot.experiments
    if es.total >= 5 and ps.total_evaluated >= 5 and ps.pass_count == 0:
        cases.append(
            _new_case(
                kind=ImmuneCaseKind.EXPERIMENT_INSTABILITY,
                severity=ImmuneCaseSeverity.MEDIUM,
                summary=(
                    f"Many experiments ({es.total}) but no patches passed evaluation "
                    f"in last {snapshot.window_hours}h."
                ),
                details={
                    "experiments_total": es.total,
                    "patches_total": ps.total_evaluated,
                },
            )
        )

    # 5) （占位）未来可以加：SAFETY_BLOCK_STORM
    # 例如从 patch_safety.jsonl 统计大量 patch 被安全阻断

    return cases
