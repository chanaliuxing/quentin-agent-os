# meta_agent/blueprint/impact_analyzer.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc, normalize_to_utc_iso
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import datetime as dt
from pathlib import Path
import json

from meta_agent.blueprint.version_store import BlueprintVersionStore, BlueprintVersionRecord
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class MetricSnapshot:
    ts_from: str; ts_to: str; total_tasks: int
    success_rate: Optional[float] = None
    error_rate: Optional[float] = None
    avg_latency_ms: Optional[float] = None

@dataclass
class BlueprintImpactItem:
    version_id: str; created_at: str; risk_level: str; target_section: str
    patch_id: str; source: str; summary: str; before: MetricSnapshot
    after: MetricSnapshot; effect_label: str
    delta_success_rate: Optional[float] = None
    delta_error_rate: Optional[float] = None

@dataclass
class BlueprintImpactReport:
    generated_at: str; window_hours: int; items: List[BlueprintImpactItem]

class BlueprintImpactAnalyzer:
    def __init__(self, blueprint_versions_root: str | Path = "data/blueprint/versions", metrics_log_path: str | Path = "logs/runtime_metrics.jsonl", window_hours: int = 24):
        self.version_store = BlueprintVersionStore(blueprint_versions_root)
        self.metrics_log_path = Path(metrics_log_path)
        self.window_hours = window_hours

    def build_report(self, limit_versions: Optional[int] = None) -> BlueprintImpactReport:
        versions = self.version_store.list_versions(limit=limit_versions)
        metrics_records = self._load_metrics_records()
        items = [self._analyze_single_version(v, metrics_records) for v in versions]
        return BlueprintImpactReport(generated_at=now_iso(), window_hours=self.window_hours, items=items)

    def _analyze_single_version(self, v: BlueprintVersionRecord, metrics: List[Dict]) -> BlueprintImpactItem:
        center_ts = dt.datetime.fromisoformat(normalize_to_utc_iso(v.created_at)).timestamp()
        w = self.window_hours * 3600.0
        
        before = self._aggregate_metrics(metrics, center_ts - w, center_ts)
        after = self._aggregate_metrics(metrics, center_ts, center_ts + w)
        
        ds = after.success_rate - before.success_rate if before.success_rate is not None and after.success_rate is not None else None
        de = after.error_rate - before.error_rate if before.error_rate is not None and after.error_rate is not None else None
        
        return BlueprintImpactItem(
            version_id=v.version_id, created_at=v.created_at, risk_level=v.risk_level,
            target_section=v.target_section, patch_id=v.patch_id, source=v.source, summary=v.summary,
            before=before, after=after, delta_success_rate=ds, delta_error_rate=de,
            effect_label=self._label_effect(ds, de)
        )

    def _load_metrics_records(self) -> List[Dict[str, Any]]:
        if not self.metrics_log_path.exists(): return []
        records = []
        with self.metrics_log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    rec = json.loads(line)
                    if "payload" in rec and "ts" in rec:
                        rec["payload"]["ts"] = dt.datetime.fromisoformat(normalize_to_utc_iso(rec["ts"])).timestamp()
                        records.append(rec["payload"])
                except: continue
        return records

    def _aggregate_metrics(self, records: List[Dict], ts_from: float, ts_to: float) -> MetricSnapshot:
        # Simplified aggregation logic
        period_recs = [r for r in records if ts_from <= r.get("ts", 0) < ts_to]
        count = len(period_recs)
        if count == 0:
            return MetricSnapshot(ts_from=dt.datetime.fromtimestamp(ts_from).isoformat(), ts_to=dt.datetime.fromtimestamp(ts_to).isoformat(), total_tasks=0)
        
        return MetricSnapshot(
            ts_from=dt.datetime.fromtimestamp(ts_from).isoformat(), ts_to=dt.datetime.fromtimestamp(ts_to).isoformat(),
            success_rate=sum(r.get("success_rate", 0) for r in period_recs) / count,
            error_rate=sum(r.get("error_rate", 0) for r in period_recs) / count,
            avg_latency_ms=sum(r.get("avg_latency_ms", 0) for r in period_recs) / count,
            total_tasks=sum(r.get("total_tasks", 0) for r in period_recs)
        )

    def _label_effect(self, ds: Optional[float], de: Optional[float], s_thr: float = 0.02, e_thr: float = 0.02) -> str:
        if ds is None or de is None: return "unknown"
        if ds > s_thr and de <= 0: return "beneficial"
        if ds >= 0 and de < -e_thr: return "beneficial"
        if ds < -s_thr or de > e_thr: return "harmful"
        return "neutral"
