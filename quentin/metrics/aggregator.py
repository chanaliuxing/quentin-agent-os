from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional

import json


@dataclass
class AggregateMetrics:
    """
    最近一段时间的汇总指标（非常简化版）：
      - total_tasks: 任务总数
      - success_tasks / error_tasks
      - success_rate / error_rate
      - avg_latency_ms
      - avg_cost_tokens
    """

    total_tasks: int = 0
    success_tasks: int = 0
    error_tasks: int = 0
    avg_latency_ms: float = 0.0
    avg_cost_tokens: float = 0.0
    # 有需要可以扩展：
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.success_tasks / self.total_tasks if self.total_tasks else 0.0

    @property
    def error_rate(self) -> float:
        return self.error_tasks / self.total_tasks if self.total_tasks else 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["error_rate"] = self.error_rate
        return d


class MetricsAggregator:
    """
    从 JsonlTraceRecorder 的事件日志中，汇总最近的任务表现。

    默认读取：
      repo_root / data / traces / events.jsonl
    """

    def __init__(self, repo_root: str | Path, trace_file: Optional[str | Path] = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        if trace_file:
            self.trace_file = Path(trace_file)
        else:
            self.trace_file = self.repo_root / "data" / "traces" / "events.jsonl"

    # --------------------------------------------------
    # 统一对外接口：
    #   max_events: 只看最近 N 条事件
    #   window_seconds: 只看最近 T 秒之内的事件
    # --------------------------------------------------
    def compute_recent_metrics(
        self,
        *,
        max_events: int = 1000,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        返回 dict 结构，包含：
          {
            "aggregate": {...AggregateMetrics...},
            "by_domain": {
              "desktop": {...},
              "legal": {...},
              ...
            },
            "raw_stats": {...一些原始计数}
          }
        """
        events = self._load_recent_events(max_events=max_events)
        if window_seconds is not None:
            events = self._filter_by_time_window(events, window_seconds=window_seconds)

        aggregate_metrics = AggregateMetrics()
        by_domain: Dict[str, AggregateMetrics] = {}

        for ev in events:
            payload = ev.get("payload", {}) or {}
            domain = payload.get("domain", "default")
            status = payload.get("status")  # "success" | "error" | None
            latency_ms = payload.get("latency_ms")
            cost_tokens = payload.get("cost_tokens")

            # 只对任务类事件统计：例如 event_type == "TASK_RESULT"
            event_type = ev.get("event_type") or ev.get("type")
            if event_type not in ("TASK_RESULT", "TASK_SUMMARY", "task_result"):
                continue

            self._update_metrics(
                aggregate_metrics,
                status=status,
                latency_ms=latency_ms,
                cost_tokens=cost_tokens,
            )

            dom_metrics = by_domain.setdefault(domain, AggregateMetrics())
            self._update_metrics(
                dom_metrics,
                status=status,
                latency_ms=latency_ms,
                cost_tokens=cost_tokens,
            )

        return {
            "aggregate": aggregate_metrics.to_dict(),
            "by_domain": {k: v.to_dict() for k, v in by_domain.items()},
            "raw_stats": {
                "num_events_scanned": len(events),
            },
        }

    # --------------------------------------------------
    # 内部：更新单个 AggregateMetrics
    # --------------------------------------------------
    def _update_metrics(
        self,
        m: AggregateMetrics,
        *,
        status: Optional[str],
        latency_ms: Optional[float],
        cost_tokens: Optional[float],
    ) -> None:
        m.total_tasks += 1
        if status == "success":
            m.success_tasks += 1
        elif status == "error":
            m.error_tasks += 1

        # 简单移动平均（这里为了代码简单，用总和 / 次数）
        if latency_ms is not None:
            # 把 sum 存到 extra，再用 total_tasks 做平均
            total_latency = m.extra.get("_latency_sum", 0.0) + float(latency_ms)
            m.extra["_latency_sum"] = total_latency
            m.avg_latency_ms = total_latency / m.total_tasks

        if cost_tokens is not None:
            total_cost = m.extra.get("_cost_sum", 0.0) + float(cost_tokens)
            m.extra["_cost_sum"] = total_cost
            m.avg_cost_tokens = total_cost / m.total_tasks

    # --------------------------------------------------
    # 内部：读最近 N 条事件
    # --------------------------------------------------
    def _load_recent_events(self, max_events: int) -> List[Dict[str, Any]]:
        if not self.trace_file.exists():
            return []

        # 为了简单：把整个文件读进内存，然后只取最后 N 行
        # （真实系统可以改成流式读最后 N 行）
        with self.trace_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        selected_lines = lines[-max_events:]
        events: List[Dict[str, Any]] = []
        for line in selected_lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                events.append(ev)
            except Exception:
                continue
        return events

    # --------------------------------------------------
    # 内部：按时间窗口过滤
    # --------------------------------------------------
    def _filter_by_time_window(
        self,
        events: List[Dict[str, Any]],
        *,
        window_seconds: int,
    ) -> List[Dict[str, Any]]:
        if not events:
            return events

        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        filtered: List[Dict[str, Any]] = []
        for ev in events:
            ts = ev.get("timestamp")
            if not ts:
                filtered.append(ev)
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                filtered.append(ev)
                continue
            if dt >= cutoff:
                filtered.append(ev)
        return filtered
