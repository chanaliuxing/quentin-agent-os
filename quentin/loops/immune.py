from __future__ import annotations

from dataclasses import dataclass, asdict, is_dataclass
from typing import Any, Dict, List, Optional
import logging
import uuid

logger = logging.getLogger(__name__)


def _trace_to_dict(t: Any) -> Dict[str, Any]:
    if isinstance(t, dict):
        return t
    if is_dataclass(t):
        return asdict(t)
    return {"raw": t}


@dataclass
class ImmuneCase:
    """
    免疫系统识别出的一个异常案例。

    - trace_id: 关联的 ExecutionTrace ID（如果有的话）
    - reason: 简短文本，说明异常原因
    - severity: "low" | "medium" | "high" | "critical"
    - trace_snapshot: 直接把 trace 的关键字段打包，方便后续分析
    - meta: 任意扩展信息（如发生时间、domain、error_type 等）
    """
    case_id: str
    trace_id: Optional[str]
    reason: str
    severity: str
    trace_snapshot: Dict[str, Any]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ImmuneLoop:
    """
    免疫循环（Immune Loop）v1 实现。

    目标：
      - 从近期 Trace 中发现异常（error / failed / cost 过高等）
      - 生成结构化 ImmuneCase 列表
      - 可选：转成自编程引擎可用的 issue 列表

    v1 的检测策略很简单：
      - status == "error" → severity = "critical"
      - status == "failed" → severity = "medium"
      - 如果 top_level_metrics.cost > cost_threshold → severity 至少 "medium"
    """

    def __init__(
        self,
        *,
        cost_threshold: float = 1e4,
        # Adding missing arguments from previous implementation to avoid breaking existing calls
        repo_root: Optional[Any] = None,
        trace_store: Optional[Any] = None,
        case_store: Optional[Any] = None,
    ) -> None:
        self.cost_threshold = cost_threshold
        self.trace_store = trace_store
        self.case_store = case_store

    def run_once(
        self,
        *,
        recent_traces: Optional[List[Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        由 RuntimeFacade 调用。

        返回：
        {
          "count": int,
          "cases": [ImmuneCase.as_dict(), ...],
        }
        """
        
        # If no traces provided but we have a trace_store, try to load them
        if recent_traces is None and self.trace_store:
             # Assume load_recent exists as per 96.md
             recent_traces = self.trace_store.load_recent(limit=200) # Default limit

        recent_traces = recent_traces or []
        
        ctx = extra_context or {}
        trace_dicts = [_trace_to_dict(t) for t in recent_traces]

        cases: List[ImmuneCase] = []
        for t in trace_dicts:
            status = t.get("status")
            if status in ("success", None):
                # 成功或未知，先跳过
                continue

            trace_id = t.get("trace_id") or t.get("id") or None
            domain = t.get("domain", "unknown")
            metrics = t.get("top_level_metrics") or {}

            severity = "medium"
            reason_parts = []

            if status == "error":
                severity = "critical"
                reason_parts.append("trace_status=error")
            elif status == "failed":
                severity = "medium"
                reason_parts.append("trace_status=failed")
            else:
                severity = "low"
                reason_parts.append(f"trace_status={status}")

            cost = metrics.get("cost") or metrics.get("token_cost") or 0.0
            if isinstance(cost, (int, float)) and cost > self.cost_threshold:
                reason_parts.append(f"cost>{self.cost_threshold}")
                if severity != "critical":
                    severity = "high"

            reason = ", ".join(reason_parts) if reason_parts else "abnormal_trace"

            case = ImmuneCase(
                case_id=f"immune::{uuid.uuid4().hex}",
                trace_id=trace_id,
                reason=reason,
                severity=severity,
                trace_snapshot=t,
                meta={"domain": domain, "context": ctx},
            )
            cases.append(case)
            
            # If case_store is available, append it (compatibility with 96.md)
            if self.case_store:
                try:
                    self.case_store.append(case)
                except Exception:
                    pass

        return {
            "count": len(cases),
            "cases": [c.to_dict() for c in cases],
        }

    def scan_recent_traces(self, limit: int = 200) -> List[ImmuneCase]:
        """
        Compatibility method for 96.md usage (called by Runtime).
        Delegates to run_once logic but returns list of cases directly.
        """
        if self.trace_store:
            traces = self.trace_store.load_recent(limit=limit)
        else:
            traces = []
            
        result = self.run_once(recent_traces=traces)
        # Convert dicts back to ImmuneCase objects if needed, but run_once returns dicts in 'cases' list elements?
        # Wait, run_once implementation above returns "cases": [c.to_dict() ...]
        # scan_recent_traces in 96.md returned List[ImmuneCase].
        # So I need to reconstruct them or adjust run_once to return objects and then to_dict them at the end.
        # However, to avoid breaking `run_once` return signature defined in this step (102.md), I will reconstruct here.
        
        cases_dicts = result.get("cases", [])
        cases_objs = []
        for d in cases_dicts:
            cases_objs.append(ImmuneCase(**d))
        return cases_objs

    def observe_trace(self, trace: Any) -> List[Any]:
        """
        Compatibility method for 96.md usage.
        """
        # Re-implement simple logic or delegate
        # 96.md logic was simple check on single trace.
        # I can just use run_once with a single trace.
        res = self.run_once(recent_traces=[trace])
        # Convert back to ImmuneSignal-like dicts?
        # 96.md returned List[ImmuneSignal]. 
        # This new implementation produces ImmuneCase.
        # I'll just return empty list or mapping to signals to avoid breaking callers if any.
        # But wait, runtime.run_task calls observe_trace.
        # I should provide a reasonable implementation.
        
        # 96.md ImmuneSignal
        from quentin.immune.schema import ImmuneSignal
        
        cases_dicts = res.get("cases", [])
        signals = []
        for c in cases_dicts:
             sig = ImmuneSignal(
                signal_id=uuid.uuid4().hex,
                source="trace",
                component="task",
                key=c.get("trace_id") or "unknown",
                severity=c.get("severity"),
                metrics={},
                context={"case_id": c.get("case_id")}
             )
             signals.append(sig)
        return signals

    # ---------------------------------------------
    # ImmuneCase → issue（给自编程引擎用）
    # ---------------------------------------------
    def cases_to_issues(self, cases: List[ImmuneCase]) -> List[Dict[str, Any]]:
        """
        将 ImmuneCase 转换为 SelfProgrammingEngine 可消费的 issue 结构。

        这里默认粒度是“模块级”：
          - target_type: "runtime_component"
          - identifier: trace_snapshot.domain
          - 我们暂时无法精确到具体文件/函数，但可以作为高层 issue 交给 ResearchLayer。
        """
        issues: List[Dict[str, Any]] = []
        for c in cases:
            domain = c.meta.get("domain", "unknown")

            target = {
                "target_type": "runtime_component",
                "identifier": domain,
                "file_path": None,
                "symbol_name": None,
                "meta": {
                    "trace_id": c.trace_id,
                    "case_id": c.case_id,
                    "reason": c.reason,
                },
            }

            issue = {
                "issue_id": c.case_id,
                "source": "immune_loop",
                "target": target,
                "reason": c.reason,
                "metrics": {
                    "severity": c.severity,
                },
            }
            issues.append(issue)

        return issues
