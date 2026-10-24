# quentin/router/metrics.py
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import uuid
import logging

logger = logging.getLogger(__name__)
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.utils.time import now_utc_iso


@dataclass
class ModelRouteRequestRecord:
    """
    一次路由请求的结构化表示，用于记录和离线训练。

    注意：这里只是“记录”，真正的调用参数由 ModelRouter 决定。
    """
    task_type: str
    importance: str = "normal"     # "low" / "normal" / "high"
    domain: str = "general"
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelRouteDecisionRecord:
    """
    ModelRouter 的决策结果（可持久化）。
    """
    model_id: str
    provider: str
    reason: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelRouteOutcomeRecord:
    """
    路由决策的结果，用于学习路由策略。
    """
    success: Optional[bool] = None
    reward: Optional[float] = None
    cost_tokens: Optional[float] = None
    latency_ms: Optional[float] = None
    quality_score: Optional[float] = None  # 人工/AI 评价

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

RouteFeedback = ModelRouteOutcomeRecord

@dataclass
class ModelRouteLogRecord:
    """
    完整的一次路由日志，用于 JSONL 持久化和训练数据。
    """
    log_id: str
    created_at: str
    request: Dict[str, Any]
    decision: Dict[str, Any]
    outcome: Dict[str, Any]
    runtime_flags: Dict[str, Any] = field(default_factory=dict)
    experiment_tags: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelRouterLogStore:
    """
    v1：简单的 JSONL 日志，用于后续 Sleep Loop / Research 的离线训练。

    - append(log_record)
    - 可扩展：按需做简单统计聚合。
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "model_router"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.base_dir / "routes.jsonl"

    def append(
        self,
        *,
        request: ModelRouteRequestRecord,
        decision: ModelRouteDecisionRecord,
        outcome: Optional[ModelRouteOutcomeRecord] = None,
        runtime_flags: Optional[Dict[str, Any]] = None,
        experiment_tags: Optional[Dict[str, Any]] = None,
    ) -> ModelRouteLogRecord:
        log = ModelRouteLogRecord(
            log_id=uuid.uuid4().hex,
            created_at=now_utc_iso(),
            request=request.to_dict(),
            decision=decision.to_dict(),
            outcome=(outcome or ModelRouteOutcomeRecord()).to_dict(),
            runtime_flags=runtime_flags or {},
            experiment_tags=experiment_tags or {},
        )
        line = json.dumps(log.to_dict(), ensure_ascii=False)
        try:
            lock = acquire_session_write_lock(session_file=self.jsonl_path)
            try:
                with self.jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("ModelRouterLogStore: failed to append route log to %s", self.jsonl_path)
        return log
