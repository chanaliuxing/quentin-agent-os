# meta_agent/immune/models.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List
from datetime import datetime
import uuid


class ImmuneCaseSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImmuneCaseKind(str, Enum):
    ERROR_SPIKE = "error_spike"              # 整体错误率暴涨
    DOMAIN_REGRESSION = "domain_regression"  # 某个 domain 失败率异常
    PATCH_FAILURE_STORM = "patch_failure_storm"
    SAFETY_BLOCK_STORM = "safety_block_storm"
    EXPERIMENT_INSTABILITY = "experiment_instability"
    OTHER = "other"


@dataclass
class ImmuneCase:
    id: str
    kind: ImmuneCaseKind
    severity: ImmuneCaseSeverity
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: now_iso())


class ImmuneActionKind(str, Enum):
    NO_OP = "no_op"

    # Skill 相关
    DISABLE_SKILL = "disable_skill"
    DOWNGRADE_SKILL = "downgrade_skill"  # 标记为 DEPRECATED / EXPERIMENTAL

    # Patch / 自改相关
    BLACKLIST_PATCH = "blacklist_patch"
    PAUSE_AUTOPATCH = "pause_autopatch"

    # 调度 / 限流
    REDUCE_TASK_BUDGET = "reduce_task_budget"
    PAUSE_TASK = "pause_task"

    # 人工介入
    REQUEST_HUMAN_REVIEW = "request_human_review"


@dataclass
class ImmuneAction:
    kind: ImmuneActionKind
    case_id: str
    target_type: str  # "skill" | "patch" | "task" | "system"
    target_id: str | None = None
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: str = field(default_factory=lambda: now_iso())
