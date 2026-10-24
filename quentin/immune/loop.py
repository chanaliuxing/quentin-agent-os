# quentin/immune/loop.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import logging

from quentin.immune.anomaly import AnomalyDetector, AnomalySignal, MetricSnapshot
from quentin.immune.store import ImmuneCaseStore, ImmuneCase
from quentin.l3.research.interface import ResearchInterface

logger = logging.getLogger(__name__)


@dataclass
class ImmuneAction:
    """
    Immune Loop 给系统的“处置建议”。

    - degrade_mode             : 是否建议进入降级模式（比如只用安全模型 / 禁用复杂实验）
    - disable_self_programming : 是否暂时关闭自编程 / patch 生成
    - revert_version           : 是否建议回滚到上一稳定版本（当前只是标记，具体回滚由外部执行）
    - notes                    : 解释/理由
    - anomaly                  : 对应的异常信号
    - immune_case_id           : 关联的 ImmuneCase，方便后续追踪
    """
    degrade_mode: bool
    disable_self_programming: bool
    revert_version: bool
    notes: str
    anomaly: Dict[str, Any]
    immune_case_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ImmuneLoop:
    """
    Immune Loop v1：异常检测 + 异常止损 + ImmuneCase 归档。

    使用方式：
    - 在 CognitiveLoop 每次尝试后调用：
      action = immune_loop.after_attempt(...)
    - 如果 action 非 None，则根据建议调整：降级、自编程开关、版本回滚等。
    """

    def __init__(
        self,
        *,
        repo_root: str | None = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        case_store: Optional[ImmuneCaseStore] = None,
        research_interface: Optional[ResearchInterface] = None,
    ) -> None:
        from pathlib import Path

        self.repo_root = Path(repo_root or ".").resolve()
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.case_store = case_store or ImmuneCaseStore(repo_root=self.repo_root)
        try:
            self.research_interface = research_interface or ResearchInterface()
        except Exception:
            logger.exception("ImmuneLoop: failed to init ResearchInterface, continuing without research integration")
            self.research_interface = None

    def after_attempt(
        self,
        *,
        goal: Any,
        metrics: Dict[str, Any],
        snapshot: MetricSnapshot,
        recent_snapshots: List[MetricSnapshot],
        recent_traces: List[Dict[str, Any]],
    ) -> Optional[ImmuneAction]:
        """
        每次尝试（一次 plan+execute 循环）结束后调用。

        - goal             : 当前目标
        - metrics          : 累计指标（total_attempts, error_attempts 等）
        - snapshot         : 当前这一轮的 MetricSnapshot
        - recent_snapshots : 最近几轮 snapshot（用于趋势分析）
        - recent_traces    : 最近几轮的 Trace 摘要，用 ImmuneCase 记录

        若返回 None：无异常；
        若返回 ImmuneAction：建议采取降级/回滚/关闭自编程等措施。
        """
        signal = self.anomaly_detector.analyze(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=recent_snapshots,
        )
        if signal is None:
            return None

        # 生成 ImmuneCase
        immune_case = self.case_store.append_case(
            goal=goal,
            anomaly=signal,
            metrics=metrics,
            recent_traces=recent_traces,
        )

        # 通知 Research Layer
        if self.research_interface:
            try:
                self.research_interface.submit_immune_case(immune_case)
            except Exception:
                logger.exception("ImmuneLoop: failed to submit immune case to ResearchInterface")

        # 从异常类型和严重级别中推导 ImmuneAction（简单 rule-based，后续可以学习优化）
        action = self._derive_action_from_signal(signal, immune_case)
        return action

    def _derive_action_from_signal(self, signal: AnomalySignal, case: ImmuneCase) -> ImmuneAction:
        degrade = False
        disable_self_prog = False
        revert = False
        notes_parts: List[str] = [signal.reason]

        if signal.anomaly_type == "high_failure_rate":
            degrade = True
            disable_self_prog = True
            notes_parts.append("High failure rate: suggest degrade mode and disable self-programming.")
        elif signal.anomaly_type == "high_cost":
            degrade = True
            notes_parts.append("High cost: suggest degrade mode and limit planning depth.")
        elif signal.anomaly_type == "high_latency":
            degrade = True
            notes_parts.append("High latency: suggest degrade mode.")
        elif signal.anomaly_type == "prediction_error_spike":
            degrade = True
            notes_parts.append("Prediction error spike: suggest degrade mode and disable reflex/predictive shortcuts.")

        # 根据严重级别进一步加码
        if signal.severity in ("high", "critical"):
            # v1 先简单设为需要考虑回滚；具体怎么回滚由外部控制
            revert = True
            notes_parts.append(f"Severity={signal.severity}: consider reverting to last stable version.")

        notes = " ".join(notes_parts)

        return ImmuneAction(
            degrade_mode=degrade,
            disable_self_programming=disable_self_prog,
            revert_version=revert,
            notes=notes,
            anomaly=signal.to_dict(),
            immune_case_id=case.case_id,
        )
