from __future__ import annotations

from dataclasses import dataclass, asdict, field
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import os
import sqlite3

from quentin.l3.research.experiments import ResearchManager
from quentin.traces.paths import resolve_events_path
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


# ---------- 数据结构 ----------

@dataclass
class BlueprintItemSpec:
    id: str
    name: str
    layer: str
    phase: str
    category: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    hints: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlueprintItemSpec":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            layer=data.get("layer", ""),
            phase=data.get("phase", ""),
            category=data.get("category", ""),
            description=data.get("description", ""),
            required_capabilities=list(data.get("required_capabilities") or []),
            hints=data.get("hints") or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintItemStatus:
    """
    一条蓝皮书条目的当前状态快照：
    - file_implemented : 对应模块文件是否存在
    - has_traces       : ExecutionTrace 中是否出现过该 capability_id
    - has_experiments  : ResearchManager 中是否有对应 experiment
    - score            : 一个 0~1 的粗略完成度（v1 简单平均）
    """

    spec: BlueprintItemSpec
    file_implemented: bool
    has_traces: bool
    has_experiments: bool
    expects_traces: bool
    expects_experiments: bool
    status: str
    confidence: float
    score: float
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = self.spec.to_dict()
        d.update(
            {
                "file_implemented": self.file_implemented,
                "has_traces": self.has_traces,
                "has_experiments": self.has_experiments,
                "expects_traces": self.expects_traces,
                "expects_experiments": self.expects_experiments,
                "status": self.status,
                "confidence": self.confidence,
                "evidence": list(self.evidence),
                "score": self.score,
            }
        )
        return d


@dataclass
class BlueprintScanReport:
    version: str
    scanned_at: str
    total_items: int
    avg_score: float
    items: List[BlueprintItemStatus]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "scanned_at": self.scanned_at,
            "total_items": self.total_items,
            "avg_score": self.avg_score,
            "items": [it.to_dict() for it in self.items],
        }


# ---------- Tracker 主体 ----------

class BlueprintGapTracker:
    """
    BlueprintGapTracker v1:

    - 读取 blueprint/spec_v3.json
    - 对每个 item 做 3 个维度的静态检查：
        1) 对应 modules 文件是否存在（粗略视为“已经动工”）
        2) ExecutionTrace 是否有该 capability 的运行记录（视为“跑通过”）
        3) ResearchManager 是否有该 capability 的实验记录（视为“有指标监控”）
    - 根据 3 项给出一个 0~1 的 completion score：
        score = (file_implemented + has_traces + has_experiments) / 3.0

    这只是 v1 的“工程可见度雷达图”，以后可以接入多 AI 评审：
    - 判断“实现质量是否达标”
    - 自动写 gap 任务 / issue
    - 驱动 SelfProgrammingEngine 去补齐缺口
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        spec_path: str | Path = "blueprint/spec_v3.json",
        # traces_store: Optional[ExecutionTraceStore] = None, # No ExecutionTraceStore in latest
        research_manager: Optional[ResearchManager] = None,
        # Updated to directly use file path for traces
        trace_file_path: str | Path = "data/traces/events.jsonl",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.spec_path = self.repo_root / spec_path
        # self.traces_store = traces_store or ExecutionTraceStore() # Removed
        self.research_manager = research_manager or ResearchManager()
        # Honor QUENTIN_TRACES_DIR override for consistency with JsonlTraceRecorder.
        # If caller explicitly provided a non-default path, respect it.
        if str(trace_file_path) == "data/traces/events.jsonl":
            self.trace_file_path = resolve_events_path(repo_root=self.repo_root)
        else:
            p = Path(trace_file_path)
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            self.trace_file_path = p
        self.kv_store_path = self.repo_root / os.getenv("QUENTIN_KVSTORE_PATH", "data/kv_store.sqlite3")

        self._items: List[BlueprintItemSpec] = []
        self._version: str = "unknown"

        self._load_spec()

    # ---------- Public API ----------

    def scan(self) -> BlueprintScanReport:
        statuses: List[BlueprintItemStatus] = []

        for item in self._items:
            file_implemented = self._check_files(item)
            expects_traces = self._expects_traces(item)
            expects_experiments = self._expects_experiments(item)
            traces_observed = self._check_traces(item) if expects_traces else False
            experiments_observed = self._check_experiments(item) if expects_experiments else False
            has_traces = traces_observed or (not expects_traces)
            has_experiments = experiments_observed or (not expects_experiments)

            score = (int(file_implemented) + int(has_traces) + int(has_experiments)) / 3.0
            status, confidence, evidence = self._classify_status(
                file_implemented=file_implemented,
                has_traces=has_traces,
                has_experiments=has_experiments,
                expects_traces=expects_traces,
                expects_experiments=expects_experiments,
                traces_observed=traces_observed,
                experiments_observed=experiments_observed,
                score=score,
            )

            statuses.append(
                BlueprintItemStatus(
                    spec=item,
                    file_implemented=file_implemented,
                    has_traces=has_traces,
                    has_experiments=has_experiments,
                    expects_traces=expects_traces,
                    expects_experiments=expects_experiments,
                    status=status,
                    confidence=confidence,
                    evidence=evidence,
                    score=score,
                )
            )

        avg_score = 0.0
        if statuses:
            avg_score = sum(s.score for s in statuses) / len(statuses)

        return BlueprintScanReport(
            version=self._version,
            scanned_at=now_iso(),
            total_items=len(statuses),
            avg_score=avg_score,
            items=statuses,
        )

    def find_item(self, item_id: str) -> Optional[BlueprintItemStatus]:
        """
        简易查询：扫描一次后按 id 找状态。
        """
        report = self.scan()
        for it in report.items:
            if it.spec.id == item_id:
                return it
        return None

    # ---------- Internal: spec ----------

    def _load_spec(self) -> None:
        if not self.spec_path.exists():
            logger.warning("BlueprintGapTracker: spec file not found: %s", self.spec_path)
            self._items = []
            self._version = "missing"
            return

        try:
            raw = json.loads(self.spec_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            logger.exception("BlueprintGapTracker: failed to read spec: %s", self.spec_path)
            raw = {}

        self._version = str(raw.get("version", "unknown"))
        items_raw = raw.get("items") or []
        self._items = [BlueprintItemSpec.from_dict(x) for x in items_raw]

    # ---------- Internal: checks ----------

    def _expects_traces(self, item: BlueprintItemSpec) -> bool:
        hints = item.hints or {}
        return bool(hints.get("trace_capability_id") or (hints.get("trace_signals") or []))

    def _expects_experiments(self, item: BlueprintItemSpec) -> bool:
        hints = item.hints or {}
        return bool(hints.get("experiment_capability"))

    def _classify_status(
        self,
        *,
        file_implemented: bool,
        has_traces: bool,
        has_experiments: bool,
        expects_traces: bool,
        expects_experiments: bool,
        traces_observed: bool,
        experiments_observed: bool,
        score: float,
    ) -> tuple[str, float, List[Dict[str, Any]]]:
        evidence: List[Dict[str, Any]] = [
            {
                "kind": "file",
                "ok": bool(file_implemented),
                "detail": "module_hint exists" if file_implemented else "module_hint missing",
                "weight": 1.0 / 3.0,
            }
        ]
        if expects_traces:
            evidence.append(
                {
                    "kind": "trace",
                    "ok": bool(traces_observed),
                    "detail": "trace signal observed" if traces_observed else "trace signal not observed",
                    "weight": 1.0 / 3.0,
                }
            )
        else:
            evidence.append(
                {
                    "kind": "trace",
                    "ok": True,
                    "detail": "trace not required by spec hints",
                    "weight": 1.0 / 3.0,
                }
            )
        if expects_experiments:
            evidence.append(
                {
                    "kind": "experiment",
                    "ok": bool(experiments_observed),
                    "detail": "experiment evidence observed" if experiments_observed else "experiment evidence not observed",
                    "weight": 1.0 / 3.0,
                }
            )
        else:
            evidence.append(
                {
                    "kind": "experiment",
                    "ok": True,
                    "detail": "experiment not required by spec hints",
                    "weight": 1.0 / 3.0,
                }
            )

        if not file_implemented:
            return "missing", score, evidence
        if has_traces and has_experiments:
            return "done", score, evidence
        if (expects_traces or expects_experiments) and (not has_traces or not has_experiments):
            return "partial", score, evidence
        return "unknown", score, evidence

    def _check_files(self, item: BlueprintItemSpec) -> bool:
        hints = item.hints or {}
        modules = hints.get("modules") or []
        for rel in modules:
            path = (self.repo_root / rel).resolve()
            if path.exists():
                return True
        return False

    def _check_traces(self, item: BlueprintItemSpec) -> bool:
        hints = item.hints or {}
        cap_id = hints.get("trace_capability_id")
        if not cap_id:
            return False
        if not self.trace_file_path.exists():
            return False

        cap_s = str(cap_id)

        def _matches_signal(event: Dict[str, Any], signal: Dict[str, Any]) -> bool:
            want_type = str(signal.get("event_type") or "").strip().lower()
            if want_type:
                have_type = str(event.get("event_type") or "").strip().lower()
                if have_type != want_type:
                    return False
            want_trace_id = str(signal.get("trace_id") or "").strip()
            if want_trace_id:
                have_trace_id = str(event.get("trace_id") or "")
                if have_trace_id != want_trace_id:
                    return False

            want_payload = signal.get("payload") or {}
            if isinstance(want_payload, dict) and want_payload:
                payload = event.get("payload") or {}
                if not isinstance(payload, dict):
                    return False
                for k, v in want_payload.items():
                    if payload.get(k) != v:
                        return False
            return True

        def _mentions_cap(event: Dict[str, Any]) -> bool:
            tid = str(event.get("trace_id") or "")
            if tid == cap_s or cap_s in tid:
                return True
            payload = event.get("payload") or {}
            # Fast path: common keys
            for k in ("capability_id", "component_id", "component", "action", "task_name"):
                v = payload.get(k)
                if isinstance(v, str) and (v == cap_s or cap_s in v):
                    return True
            # Fallback: substring scan over payload JSON for best-effort matching.
            try:
                blob = json.dumps(payload, ensure_ascii=False)
                return cap_s in blob
            except Exception:
                return False

        try:
            signals = hints.get("trace_signals") or []
            signals = [s for s in signals if isinstance(s, dict)]
            with self.trace_file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if signals:
                        for s in signals:
                            if _matches_signal(event, s):
                                return True
                    else:
                        if _mentions_cap(event):
                            return True
        except Exception:
            logger.exception(
                "BlueprintGapTracker._check_traces: error while scanning traces from %s",
                self.trace_file_path,
            )
        return False

    def _check_experiments(self, item: BlueprintItemSpec) -> bool:
        hints = item.hints or {}
        cap = hints.get("experiment_capability")
        if not cap:
            return False
        cap_s = str(cap)

        # Prefer KVStore-backed experiments (ResearchInterfaceV3 / ExperimentOrchestrator).
        if self._check_experiments_kv(target_module=cap_s):
            return True

        try:
            exps = self.research_manager.list_experiments()
        except Exception:
            logger.exception("BlueprintGapTracker._check_experiments: failed to list experiments")
            return False

        for e in exps or []:
            # ResearchManager.list_experiments() currently returns experiment IDs (strings).
            if isinstance(e, str):
                if e == cap_s or cap_s in e:
                    return True
                # Best-effort: load config and match target_component / description.
                try:
                    store = getattr(self.research_manager, "store", None)
                    if store is not None and hasattr(store, "load_config"):
                        cfg = store.load_config(e)  # type: ignore[call-arg]
                        if cfg is not None:
                            meta = getattr(cfg, "meta", {}) or {}
                            target_component = str(meta.get("target_component") or "")
                            if target_component and (target_component == cap_s or cap_s in target_component):
                                return True
                            desc = str(getattr(cfg, "description", "") or "")
                            if desc and (desc == cap_s or cap_s in desc):
                                return True
                except Exception:
                    pass
                continue
            if isinstance(e, dict):
                if str(e.get("capability") or "") == cap_s or str(e.get("purpose") or "") == cap_s:
                    return True
                continue
            if getattr(e, "capability", None) == cap or getattr(e, "purpose", None) == cap:
                return True
        return False

    def _check_experiments_kv(self, *, target_module: str) -> bool:
        """
        Detect experiments created via the canonical L3 orchestrator (KVStore-backed).

        Data model (see `quentin/infra/storage/kv_store.py` and `quentin/l3/research/experiment_orchestrator.py`):
        - kv key `exp:index:all` -> list of experiment ids
        - kv key `exp:record:<experiment_id>` -> ExperimentRecord dict (includes `config.target_module`)
        """
        path = Path(self.kv_store_path)
        if not path.exists():
            return False
        want = str(target_module or "").strip()
        if not want:
            return False

        def _get(conn: sqlite3.Connection, key: str) -> Optional[str]:
            cur = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else None

        try:
            conn = sqlite3.connect(str(path))
        except Exception:
            return False
        try:
            raw_idx = _get(conn, "exp:index:all")
            if not raw_idx:
                return False
            try:
                ids = json.loads(raw_idx)
            except Exception:
                ids = []
            if not isinstance(ids, list):
                return False

            # Prefer scanning from most-recent to oldest. We bound the scan for very large stores,
            # but the bound is intentionally generous to avoid false negatives for older experiments.
            uniq: list[str] = []
            seen: set[str] = set()
            for exp_id in reversed(ids):
                if not exp_id:
                    continue
                s = str(exp_id)
                if s in seen:
                    continue
                seen.add(s)
                uniq.append(s)
            # uniq is most-recent first
            max_check = min(len(uniq), 5000)
            for exp_id in uniq[:max_check]:
                if not exp_id:
                    continue
                raw_rec = _get(conn, f"exp:record:{exp_id}")
                if not raw_rec:
                    continue
                try:
                    rec = json.loads(raw_rec)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                cfg = rec.get("config") or {}
                if not isinstance(cfg, dict):
                    continue
                target = str(cfg.get("target_module") or "").strip()
                if target == want:
                    return True
        except Exception:
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return False
