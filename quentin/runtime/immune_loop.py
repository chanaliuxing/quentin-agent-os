from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, List
from collections import deque

from quentin.traces.core import TraceRecorder, new_trace_event, TraceEventType
from quentin.utils.time import now_iso


@dataclass
class ImmuneAction:
    """
    当检测到异常时，免疫循环返回的“建议动作”。

    action_type:
      - "none"             : 不做任何操作
      - "degrade"          : 降级（关闭部分功能/自改）
      - "rollback"         : 回滚到上一稳定版本
      - "reduce_exploration": 降低探索强度
      - "pause_self_programming": 暂停自编程功能
    """
    action_type: str
    reason: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyDetectorConfig:
    window_size: int = 100
    error_rate_threshold: float = 0.3
    max_latency_ms: Optional[float] = None
    # P0: Local model tolerance multiplier (e.g. 3.0x threshold for local models)
    local_tolerance_multiplier: float = 3.0


class ImmuneLoop:
    """
    Immune Loop 骨架：

      - 维护一个滑动窗口（最近 N 次 task 的结果）
      - 计算 error rate / latency 等指标
      - 当超过阈值时，给出 ImmuneAction（降级/回滚/暂停自编程）
      - 同时写 Trace，方便后续 Research Layer 分析免疫事件
    """

    def __init__(
        self,
        *,
        config: AnomalyDetectorConfig,
        trace_recorder: TraceRecorder,
    ) -> None:
        self.config = config
        self.trace_recorder = trace_recorder
        self._window: deque[Dict[str, Any]] = deque(maxlen=config.window_size)

    def record_task_outcome(
        self,
        *,
        trace_id: str,
        task_id: str,
        status: str,
        latency_ms: Optional[float] = None,
        cost_tokens: Optional[float] = None,
        provider: str = "unknown",
    ) -> None:
        self._window.append(
            {
                "trace_id": trace_id,
                "task_id": task_id,
                "status": status,
                "latency_ms": latency_ms,
                "cost_tokens": cost_tokens,
                "provider": provider,
                "timestamp": now_iso(),
            }
        )

    def analyze_and_maybe_act(self) -> ImmuneAction:
        if not self._window:
            return ImmuneAction(action_type="none", reason="no_data", metadata={})

        total = len(self._window)
        errors = sum(1 for x in self._window if x["status"] == "failed")
        error_rate = errors / total

        max_lat = None
        current_latency_threshold = self.config.max_latency_ms
        
        # Determine if the window is dominated by local models
        local_count = sum(1 for x in self._window if str(x.get("provider", "")).lower() == "ollama")
        is_local_heavy = local_count > (total / 2)

        if current_latency_threshold is not None:
            if is_local_heavy:
                # [Porting openclaw logic] Apply maximum tolerance for local environments
                current_latency_threshold *= self.config.local_tolerance_multiplier
            
            latencies = [x["latency_ms"] for x in self._window if x["latency_ms"] is not None]
            if latencies:
                max_lat = max(latencies)

        # 简单规则：可以以后改成 ML
        if error_rate >= self.config.error_rate_threshold:
            action = ImmuneAction(
                action_type="degrade",
                reason=f"high_error_rate={error_rate:.3f}",
                metadata={"window_size": total, "errors": errors},
            )
        elif max_lat is not None and current_latency_threshold is not None and max_lat > current_latency_threshold:
            action = ImmuneAction(
                action_type="reduce_exploration",
                reason=f"high_latency={max_lat}ms (threshold={current_latency_threshold}ms)",
                metadata={"window_size": total, "local_heavy": is_local_heavy},
            )
        else:
            action = ImmuneAction(
                action_type="none",
                reason="within_threshold",
                metadata={"error_rate": error_rate},
            )

        # 写 Trace
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id="immune-loop",
                event_type=TraceEventType.IMMUNE,
                payload=action.to_dict(),
            )
        )
        return action
