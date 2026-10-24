from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import logging
import os
import uuid
import statistics

from quentin.traces.execution_trace import ExecutionTraceStore, ExecutionTrace
from quentin.l3.research.experiments import ResearchManager
from quentin.self_programming.legacy_selfprog.engine import SelfProgrammingEngine, PatchTaskSpec
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.loops.immune_defaults import load_immune_loop_defaults
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


# ---------- 数据结构 ----------

@dataclass
class ImmuneConfig:
    """
    ImmuneLoop 的基础配置（v1）：

    - window_minutes      : 分析时间窗口长度
    - min_samples         : 每个 component 至少多少条 Trace 才做判断
    - error_rate_threshold: 若失败率超过该阈值，视为异常
    - latency_ms_threshold: 若平均 latency_ms 超过该阈值，视为异常（可选）
    - enable_self_fix     : 是否允许自动触发 SelfProgrammingEngine
    - max_self_fix_per_run: 每次运行最多触发多少个自修补
    - component_to_module : 映射 component_id -> 代码路径（用于自修补）
    """

    window_minutes: int = 60
    min_samples: int = 10
    error_rate_threshold: float = 0.3
    latency_ms_threshold: Optional[float] = None
    enable_self_fix: bool = False
    max_self_fix_per_run: int = 1
    component_to_module: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImmuneCase:
    """
    一次异常检测记录：

    - case_id        : 唯一 ID
    - component_id   : 哪个组件/loop 出现问题
    - blueprint_cap  : 对应蓝皮书 capability_id（若有）
    - time_window    : 分析窗口 [start, end]
    - num_samples    : 统计中参与的 Trace 数量
    - error_rate     : 失败率
    - avg_latency_ms : 平均延迟（若有）
    - severity       : 严重程度（low/medium/high）
    - suggested_action: 建议动作（降级/自修补/仅观察）
    - created_at     : 记录时间
    """

    case_id: str
    component_id: str
    blueprint_cap: Optional[str]
    time_window_start: str
    time_window_end: str
    num_samples: int
    error_rate: float
    avg_latency_ms: Optional[float]
    severity: str
    suggested_action: str
    created_at: str = field(default_factory=lambda: now_iso())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- ImmuneLoop ----------

class ImmuneLoop:
    """
    ImmuneLoop v1：

    - 从 ExecutionTraceStore 中读取最近一段时间的 Trace
    - 按 component_id 分组，统计：
        - 样本数
        - error_rate (1 - success_ratio)
        - avg_latency_ms (如果 metrics 中有 latency_ms)
    - 若某个 component 超过阈值，则生成 ImmuneCase：
        - severity: 根据 error_rate 和 latency 进行简单判断
        - suggested_action: e.g. 'observe', 'degrade', 'self_fix'
    - 将 ImmuneCase:
        - 写入 data/immune_cases.jsonl
        - 记录到 ResearchManager（capability: immune_loop）
        - 记录 ExecutionTrace（blueprint_capability_id="immune_loop"）
    - 如果启用 enable_self_fix:
        - 根据 component_to_module 映射，触发 SelfProgrammingEngine 做一次自修补实验
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        config: Optional[ImmuneConfig] = None,
        traces_store: Optional[ExecutionTraceStore] = None,
        research_manager: Optional[ResearchManager] = None,
        selfprog_engine: Optional[SelfProgrammingEngine] = None,
        immune_cases_path: str | Path = "data/immune_cases.jsonl",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = config or ImmuneConfig()
        self._defaults_path = self.repo_root / "config" / "immune_loop_config.json"
        override = (os.getenv("QUENTIN_IMMUNE_DEFAULTS_PATH") or "").strip()
        if override:
            try:
                self._defaults_path = Path(override).expanduser().resolve()
            except Exception:
                pass

        enable_defaults = os.getenv("QUENTIN_IMMUNE_DEFAULTS_ENABLE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Only apply defaults when the caller didn't explicitly pass a config. This avoids
        # surprising behavior in unit tests and call sites that set config deliberately.
        if enable_defaults and config is None:
            defaults = load_immune_loop_defaults(self._defaults_path)
            if defaults is not None:
                if defaults.window_minutes is not None:
                    self.config.window_minutes = int(defaults.window_minutes)
                if defaults.min_samples is not None:
                    self.config.min_samples = int(defaults.min_samples)
                if defaults.error_rate_threshold is not None:
                    self.config.error_rate_threshold = float(defaults.error_rate_threshold)
                if defaults.latency_ms_threshold is not None:
                    self.config.latency_ms_threshold = float(defaults.latency_ms_threshold)
        self.traces_store = traces_store or ExecutionTraceStore(repo_root=self.repo_root)
        self.research_manager = research_manager or ResearchManager()
        self.selfprog_engine = selfprog_engine or SelfProgrammingEngine(repo_root=self.repo_root)
        self.immune_cases_path = self.repo_root / immune_cases_path
        self.immune_cases_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 对外入口：执行一次 Immune 检查 ----

    def run_once(self) -> List[ImmuneCase]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.config.window_minutes)

        # 1) 收集窗口内 Trace
        traces = list(self._iter_traces_since(window_start))

        # 2) 按 component 聚合
        stats = self._aggregate_by_component(traces)

        # 3) 检测异常并生成 ImmuneCase
        cases: List[ImmuneCase] = []
        for comp_id, comp_stats in stats.items():
            if comp_stats["num"] < self.config.min_samples:
                continue
            case = self._detect_anomaly_for_component(
                component_id=comp_id,
                stats=comp_stats,
                window_start=window_start,
                window_end=now,
            )
            if case is not None:
                cases.append(case)
                self._save_immune_case(case)
                self._record_research(case)
                self._record_trace(case)

        # 4) 触发自修补（有限个）
        if self.config.enable_self_fix and self.config.max_self_fix_per_run > 0:
            self._run_self_fix_for_cases(cases)

        return cases

    # ---- 内部：Trace 读取 & 聚合 ----

    def _iter_traces_since(self, since: datetime):
        """
        简单实现：读取最近 N 条 Trace，然后按时间过滤。
        ExecutionTraceStore 具体实现可以用 SQLite / JSONL / 其它。
        """
        # v1 先用 limit=5000 做一个粗略的时间过滤
        # Normalize to timezone-aware UTC for stable comparisons.
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        for tr in self.traces_store.iter_traces(limit=5000):
            try:
                t = datetime.fromisoformat(tr.end_time)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if t >= since:
                yield tr

    def _aggregate_by_component(self, traces: List[ExecutionTrace]) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for tr in traces:
            comp_id = tr.component_id or "unknown"
            s = stats.setdefault(
                comp_id,
                {
                    "num": 0,
                    "num_success": 0,
                    "latencies": [],
                    "blueprint_caps": set(),
                },
            )
            s["num"] += 1
            if tr.success:
                s["num_success"] += 1
            # latency_ms 可能存在于 metrics 里
            if tr.metrics and "latency_ms" in tr.metrics:
                try:
                    s["latencies"].append(float(tr.metrics["latency_ms"]))
                except Exception:
                    pass
            if tr.blueprint_capability_id:
                s["blueprint_caps"].add(tr.blueprint_capability_id)
        return stats

    # ---- 内部：检测异常 & 生成 ImmuneCase ----

    def _detect_anomaly_for_component(
        self,
        *,
        component_id: str,
        stats: Dict[str, Any],
        window_start: datetime,
        window_end: datetime,
    ) -> Optional[ImmuneCase]:
        num = stats["num"]
        num_success = stats["num_success"]
        error_rate = 1.0 - (num_success / max(1, num))
        latencies = stats["latencies"]
        avg_latency = statistics.mean(latencies) if latencies else None
        caps = stats["blueprint_caps"]
        blueprint_cap = next(iter(caps)) if caps else None

        if error_rate < self.config.error_rate_threshold and (
            self.config.latency_ms_threshold is None
            or avg_latency is None
            or avg_latency < self.config.latency_ms_threshold
        ):
            # 没有触发异常
            return None

        severity = self._classify_severity(error_rate=error_rate, avg_latency=avg_latency)
        suggested_action = self._suggest_action(severity=severity, component_id=component_id)

        case = ImmuneCase(
            case_id=str(uuid.uuid4()),
            component_id=component_id,
            blueprint_cap=blueprint_cap,
            time_window_start=window_start.isoformat(),
            time_window_end=window_end.isoformat(),
            num_samples=num,
            error_rate=error_rate,
            avg_latency_ms=avg_latency,
            severity=severity,
            suggested_action=suggested_action,
        )
        return case

    def _classify_severity(
        self,
        *,
        error_rate: float,
        avg_latency: Optional[float],
    ) -> str:
        """
        非常粗糙的严重度划分，可以后续用 ML / 学习策略替换。
        """
        if error_rate >= 0.8:
            return "high"
        if error_rate >= 0.5:
            return "medium"
        if self.config.latency_ms_threshold is not None and avg_latency is not None:
            if avg_latency >= self.config.latency_ms_threshold * 1.5:
                return "medium"
        return "low"

    def _suggest_action(self, *, severity: str, component_id: str) -> str:
        """
        v1 策略：
        - low    : "observe"
        - medium : 若有模块映射，则 "self_fix", 否则 "degrade"
        - high   : 若有模块映射，则 "self_fix", 否则 "degrade"
        """
        has_module = component_id in self.config.component_to_module
        if severity == "low":
            return "observe"
        if severity in ("medium", "high"):
            if has_module:
                return "self_fix"
            return "degrade"
        return "observe"

    # ---- 内部：ImmuneCase 持久化 ----

    def _save_immune_case(self, case: ImmuneCase) -> None:
        try:
            lock = acquire_session_write_lock(session_file=self.immune_cases_path)
            try:
                with self.immune_cases_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("ImmuneLoop._save_immune_case: failed to append case")

    # ---- 内部：Research & Trace ----

    def _record_research(self, case: ImmuneCase) -> None:
        rm = self.research_manager
        capability = "immune_loop"
        requirement_id = "anomaly_detection_quality"

        try:
            exps = rm.list_experiments()
        except Exception:
            logger.exception("ImmuneLoop._record_research: failed to list experiments")
            return

        exp = None
        for e in exps:
            if e.capability == capability and e.requirement_id == requirement_id:
                exp = e
                break
        if exp is None:
            exp = rm.create_experiment(
                name="ImmuneLoop",
                purpose="immune_anomaly_detection",
                capability=capability,
                requirement_id=requirement_id,
                tags=["immune", "anomaly"],
            )

        metrics = {
            "error_rate": case.error_rate,
            "severity_high_flag": 1.0 if case.severity == "high" else 0.0,
        }

        rm.record_run(
            experiment_id=exp.experiment_id,
            variant_id="immune_v1",
            metrics=metrics,
            context={
                "immune_case": case.to_dict(),
            },
        )

    def _record_trace(self, case: ImmuneCase) -> None:
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            task_id=case.case_id,
            component_id="immune_loop.v1",
            blueprint_capability_id="immune_loop",  # 对应 blueprint/spec_v3.json
            target_module="quentin/loops/immune_loop.py",
            target_symbol="ImmuneLoop.run_once",
            success=True,
            error_type=None,
            error_message=None,
            start_time=case.time_window_start,
            end_time=case.time_window_end,
            metrics={
                "error_rate": case.error_rate,
            },
            tags={
                "component_id": case.component_id,
                "severity": case.severity,
                "suggested_action": case.suggested_action,
            },
        )
        self.traces_store.append(trace)

    # ---- 内部：自修补触发 ----

    def _run_self_fix_for_cases(self, cases: List[ImmuneCase]) -> None:
        """
        按严重程度排序，从高到低，最多触发 max_self_fix_per_run 个自修补。
        """
        if not cases:
            return

        candidates = [c for c in cases if c.suggested_action == "self_fix"]
        if not candidates:
            return

        # 简单按 error_rate 排序
        candidates.sort(key=lambda c: c.error_rate, reverse=True)
        limit = min(self.config.max_self_fix_per_run, len(candidates))

        for i in range(limit):
            case = candidates[i]
            module_path = self.config.component_to_module.get(case.component_id)
            if not module_path:
                continue

            reason = (
                f"ImmuneLoop detected high error_rate={case.error_rate:.2f}"
                f" for component {case.component_id} in the last"
                f" {self.config.window_minutes} minutes. "
                f"Attempting a self-fix patch."
            )

            task = PatchTaskSpec(
                target_path=module_path,
                reason=reason,
                domain="core",
                environment="sandbox",
                risk_level="high",
                context_snippet=json.dumps(
                    {
                        "immune_case": case.to_dict(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            try:
                result = self.selfprog_engine.propose_and_apply_patch(task)
                logger.info(
                    "ImmuneLoop self-fix result for %s: success=%s applied=%s",
                    case.component_id,
                    result.success,
                    result.applied,
                )
            except Exception:
                logger.exception("ImmuneLoop._run_self_fix_for_cases: self fix failed for %s", case.component_id)
