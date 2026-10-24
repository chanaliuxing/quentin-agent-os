# quentin/immune/anomaly.py
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """
    用于描述某一时刻的一些关键指标。
    这里的字段你可以随时扩展，当前只做示例。
    """
    attempt_index: int
    total_attempts: int
    success_attempts: int
    error_attempts: int
    cost_tokens: float = 0.0
    latency_ms: float = 0.0
    reward_score: float = 0.0  # 可以是任务收益、评分等
    # v3.1+: predictive/context metrics (best-effort, optional)
    tool_call_count: int = 0
    prediction_error_count: int = 0
    prediction_error_rate: float = 0.0
    situation_id: Optional[str] = None
    situation_confidence: Optional[float] = None
    attention_reduction_ratio: Optional[float] = None
    context_misclass_rate: Optional[float] = None
    unexpected_ui_rate: Optional[float] = None

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "total_attempts": self.total_attempts,
            "success_attempts": self.success_attempts,
            "error_attempts": self.error_attempts,
            "cost_tokens": self.cost_tokens,
            "latency_ms": self.latency_ms,
            "reward_score": self.reward_score,
            "tool_call_count": self.tool_call_count,
            "prediction_error_count": self.prediction_error_count,
            "prediction_error_rate": self.prediction_error_rate,
            "situation_id": self.situation_id,
            "situation_confidence": self.situation_confidence,
            "attention_reduction_ratio": self.attention_reduction_ratio,
            "context_misclass_rate": self.context_misclass_rate,
            "unexpected_ui_rate": self.unexpected_ui_rate,
            "timestamp": self.timestamp,
        }


@dataclass
class AnomalySignal:
    """
    异常信号：Immune Loop 的输入。
    """
    anomaly_type: str          # 如 "high_failure_rate" / "high_cost" / "timeout" 等
    severity: str              # "low" | "medium" | "high" | "critical"
    reason: str                # 人类可读的异常描述
    suggested_actions: List[str]  # 如 ["degrade_mode", "disable_self_programming"]

    metrics: Dict[str, Any]
    created_at: str = datetime.now(UTC).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "reason": self.reason,
            "suggested_actions": self.suggested_actions,
            "metrics": self.metrics,
            "created_at": self.created_at,
        }


class AnomalyDetector:
    """
    v1: 简单规则 + 日志，后续可以接统计/ML 模型。

    使用方式：
    - detector = AnomalyDetector()
    - signal = detector.analyze(goal, metrics, snapshot, recent_snapshots)
    - 若 signal 为 None = 正常；否则表示检测到异常。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        # 一些默认阈值
        self.failure_rate_threshold = float(self.config.get("failure_rate_threshold", 0.8))
        self.min_attempts_for_failure = int(self.config.get("min_attempts_for_failure", 3))
        self.max_tokens_per_goal = float(self.config.get("max_tokens_per_goal", 50_000))
        self._is_local_runtime = self._detect_local_runtime()
        self.max_latency_ms = self._resolve_max_latency_ms()
        self.min_attempts_for_latency = self._resolve_min_attempts_for_latency()
        self.min_attempts_for_reward = int(self.config.get("min_attempts_for_reward", 5))
        self.min_avg_reward = float(self.config.get("min_avg_reward", 0.2))
        self.reward_window = int(self.config.get("reward_window", 10))
        self.error_burst_window = int(self.config.get("error_burst_window", 5))
        self.error_burst_threshold = float(self.config.get("error_burst_threshold", 0.9))
        self.prediction_error_rate_threshold = float(self.config.get("prediction_error_rate_threshold", 0.6))

    @staticmethod
    def _detect_local_runtime() -> bool:
        provider = str(os.getenv("LLM_PROVIDER", "") or "").strip().lower()
        if provider in {"ollama", "local", "lmstudio"}:
            return True

        base_url = str(os.getenv("LLM_BASE_URL", "") or "").strip()
        if base_url:
            try:
                host = (urlparse(base_url).hostname or "").lower()
                if host in {"localhost", "127.0.0.1", "::1"}:
                    return True
            except Exception:
                pass

        model_name = str(os.getenv("LLM_MODEL", "") or "").strip()
        locals_raw = str(os.getenv("LLM_LOCAL_MODELS", "") or "").strip()
        if model_name and locals_raw:
            local_models = {x.strip() for x in locals_raw.split(",") if x.strip()}
            if model_name in local_models:
                return True

        return False

    def _resolve_max_latency_ms(self) -> float:
        env_global = str(os.getenv("QUENTIN_IMMUNE_MAX_LATENCY_MS", "") or "").strip()
        env_local = str(os.getenv("QUENTIN_IMMUNE_MAX_LATENCY_MS_LOCAL", "") or "").strip()
        env_remote = str(os.getenv("QUENTIN_IMMUNE_MAX_LATENCY_MS_REMOTE", "") or "").strip()

        if self._is_local_runtime:
            if env_local:
                return float(env_local)
            if env_global:
                return float(env_global)
            return float(self.config.get("max_latency_ms_local", 600_000))  # 10 min for local models

        if env_remote:
            return float(env_remote)
        if env_global:
            return float(env_global)
        return float(self.config.get("max_latency_ms", 60_000))

    def _resolve_min_attempts_for_latency(self) -> int:
        if self._is_local_runtime:
            raw = str(os.getenv("QUENTIN_IMMUNE_MIN_ATTEMPTS_FOR_LATENCY_LOCAL", "") or "").strip()
            if raw:
                return max(1, int(raw))
            return max(1, int(self.config.get("min_attempts_for_latency_local", 2)))
        raw = str(os.getenv("QUENTIN_IMMUNE_MIN_ATTEMPTS_FOR_LATENCY_REMOTE", "") or "").strip()
        if raw:
            return max(1, int(raw))
        return max(1, int(self.config.get("min_attempts_for_latency_remote", 1)))

    def analyze(
        self,
        *,
        goal: Any,
        metrics: Dict[str, Any],
        snapshot: MetricSnapshot,
        recent_snapshots: List[MetricSnapshot],
    ) -> Optional[AnomalySignal]:
        """
        根据 metrics + 当前 snapshot + 最近的历史，判断是否出现异常。
        """
        total = snapshot.total_attempts
        errors = snapshot.error_attempts
        failure_rate = (errors / total) if total > 0 else 0.0
        cost_tokens = snapshot.cost_tokens
        latency_ms = snapshot.latency_ms
        prediction_error_rate = None
        try:
            if getattr(snapshot, "prediction_error_rate", None) is not None:
                prediction_error_rate = float(snapshot.prediction_error_rate or 0.0)
            elif isinstance(metrics, dict) and metrics.get("prediction_error_rate") is not None:
                prediction_error_rate = float(metrics.get("prediction_error_rate") or 0.0)
        except Exception:
            prediction_error_rate = None

        context_misclass_rate = None
        try:
            if getattr(snapshot, "context_misclass_rate", None) is not None:
                context_misclass_rate = float(snapshot.context_misclass_rate or 0.0)
        except Exception:
            context_misclass_rate = None

        # 1) 高失败率
        if total >= self.min_attempts_for_failure and failure_rate >= self.failure_rate_threshold:
            reason = (
                f"High failure rate detected: {failure_rate:.2f} over {total} attempts "
                f"(threshold={self.failure_rate_threshold})."
            )
            logger.warning("[AnomalyDetector] %s", reason)
            return AnomalySignal(
                anomaly_type="high_failure_rate",
                severity="high",
                reason=reason,
                suggested_actions=["degrade_mode", "disable_self_programming", "trigger_reflection"],
                metrics={
                    "failure_rate": failure_rate,
                    "total_attempts": total,
                    "error_attempts": errors,
                },
            )

        # 1.1) 预测误差过高（v3.1+）：优先回退 Planner 深思/禁用反射
        if prediction_error_rate is not None and prediction_error_rate >= self.prediction_error_rate_threshold:
            reason = (
                f"High prediction_error_rate detected: {prediction_error_rate:.2f} "
                f"(threshold={self.prediction_error_rate_threshold})."
            )
            logger.warning("[AnomalyDetector] %s", reason)
            return AnomalySignal(
                anomaly_type="prediction_error_spike",
                severity="medium",
                reason=reason,
                suggested_actions=["degrade_mode", "disable_reflex_mode", "trigger_reflection"],
                metrics={
                    "prediction_error_rate": prediction_error_rate,
                },
            )

        # 1.2) 上下文/情境判定持续低置信（proxy）：降低 Perception 影响/回退深思
        try:
            misclass_th = float(self.config.get("context_misclass_rate_threshold", 0.75))
        except Exception:
            misclass_th = 0.75
        if context_misclass_rate is not None and context_misclass_rate >= misclass_th:
            reason = (
                f"High context_misclass_rate detected (proxy): {context_misclass_rate:.2f} "
                f"(threshold={misclass_th})."
            )
            logger.warning("[AnomalyDetector] %s", reason)
            return AnomalySignal(
                anomaly_type="context_misclass_spike",
                severity="low",
                reason=reason,
                suggested_actions=["degrade_mode", "disable_reflex_mode"],
                metrics={
                    "context_misclass_rate": context_misclass_rate,
                },
            )

        # 2) 成本过高
        if cost_tokens >= self.max_tokens_per_goal > 0:
            reason = (
                f"High token cost detected: {cost_tokens} tokens used for this goal "
                f"(threshold={self.max_tokens_per_goal})."
            )
            logger.warning("[AnomalyDetector] %s", reason)
            return AnomalySignal(
                anomaly_type="high_cost",
                severity="medium",
                reason=reason,
                suggested_actions=["degrade_mode", "limit_planning_depth"],
                metrics={
                    "cost_tokens": cost_tokens,
                },
            )

        # 3) 延迟过高
        if (
            total >= self.min_attempts_for_latency
            and latency_ms >= self.max_latency_ms > 0
        ):
            reason = (
                f"High latency detected: {latency_ms:.1f} ms "
                f"(threshold={self.max_latency_ms})."
            )
            logger.warning("[AnomalyDetector] %s", reason)
            return AnomalySignal(
                anomaly_type="high_latency",
                severity="medium",
                reason=reason,
                suggested_actions=["degrade_mode"],
                metrics={
                    "latency_ms": latency_ms,
                },
            )

        # 4) Reward 持续偏低（简单滑动窗口）
        if total >= self.min_attempts_for_reward and recent_snapshots:
            window = recent_snapshots[-max(1, self.reward_window) :]
            vals = [float(s.reward_score or 0.0) for s in window]
            avg = sum(vals) / max(1, len(vals))
            if avg < self.min_avg_reward:
                reason = (
                    f"Low average reward detected: avg_reward={avg:.3f} "
                    f"over window={len(vals)} (threshold={self.min_avg_reward})."
                )
                logger.warning("[AnomalyDetector] %s", reason)
                return AnomalySignal(
                    anomaly_type="low_reward",
                    severity="medium",
                    reason=reason,
                    suggested_actions=["trigger_reflection", "degrade_mode"],
                    metrics={"avg_reward": avg, "window": len(vals)},
                )

        # 5) Error burst（最近窗口接近全错）
        if total >= self.min_attempts_for_failure and recent_snapshots:
            window = recent_snapshots[-max(1, self.error_burst_window) :]
            total_w = sum(max(0, int(s.total_attempts or 0)) for s in window)
            errs_w = sum(max(0, int(s.error_attempts or 0)) for s in window)
            burst_rate = (errs_w / total_w) if total_w > 0 else 0.0
            if burst_rate >= self.error_burst_threshold and total_w >= self.min_attempts_for_failure:
                reason = (
                    f"Error burst detected: error_rate={burst_rate:.2f} "
                    f"over recent window attempts={total_w} (threshold={self.error_burst_threshold})."
                )
                logger.warning("[AnomalyDetector] %s", reason)
                return AnomalySignal(
                    anomaly_type="error_burst",
                    severity="high",
                    reason=reason,
                    suggested_actions=["degrade_mode", "disable_self_programming", "trigger_reflection"],
                    metrics={"error_rate": burst_rate, "window_attempts": total_w},
                )

        return None
