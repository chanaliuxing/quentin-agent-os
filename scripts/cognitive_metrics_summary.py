#!/usr/bin/env python3
"""
Minimal v3.1+ cognitive metrics summary from JSONL traces.

This script is intentionally lightweight and pluggable:
- No DB dependencies
- Works on `data/traces/events.jsonl` emitted by JsonlTraceRecorder

Usage:
  python -m scripts.cognitive_metrics_summary
  python -m scripts.cognitive_metrics_summary --trace-path data/traces/events.jsonl --json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sqlite3

from quentin.traces.paths import resolve_events_path


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


@dataclass
class Summary:
    trace_path: str
    memory_db_path: Optional[str]
    total_events: int
    planning_events: int
    perception_snapshots: int
    reflex_hits: int
    reflex_fails: int
    capability_gaps: int
    attention_reduction_avg: Optional[float]
    attention_hit_rate: Optional[float]
    situation_confidence_avg: Optional[float]
    context_misclass_rate_avg: Optional[float]
    prediction_error_rate_avg: Optional[float]
    tool_call_count_avg: Optional[float]
    fallback_to_planner_rate_avg: Optional[float]
    top_prediction_error_types: List[Tuple[str, int]]
    gist_injection_rate: Optional[float]
    gist_injected_avg_count: Optional[float]
    memory_kind_counts: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _avg(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / max(1, len(vals))


def _memory_kind_counts(db_path: Path) -> Dict[str, int]:
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return {}
    try:
        cur = conn.execute("SELECT kind, COUNT(1) FROM memories GROUP BY kind")
        out: Dict[str, int] = {}
        for kind, cnt in cur.fetchall():
            out[str(kind)] = int(cnt)
        return out
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def summarize_trace_file(path: Path) -> Summary:
    total = 0
    planning_events = 0
    perception = 0
    reflex = 0
    reflex_fails = 0
    gaps = 0
    attention_ratios: List[float] = []
    attention_hits = 0
    situation_confidences: List[float] = []
    context_misclass_rates: List[float] = []
    pred_error_rates: List[float] = []
    tool_call_counts: List[float] = []
    fallback_rates: List[float] = []
    pred_err_types: Dict[str, int] = {}
    gist_injected_events = 0
    gist_counts: List[float] = []

    if not path.exists():
        return Summary(
            trace_path=str(path),
            memory_db_path=None,
            total_events=0,
            planning_events=0,
            perception_snapshots=0,
            reflex_hits=0,
            reflex_fails=0,
            capability_gaps=0,
            attention_reduction_avg=None,
            attention_hit_rate=None,
            situation_confidence_avg=None,
            context_misclass_rate_avg=None,
            prediction_error_rate_avg=None,
            tool_call_count_avg=None,
            fallback_to_planner_rate_avg=None,
            top_prediction_error_types=[],
            gist_injection_rate=None,
            gist_injected_avg_count=None,
            memory_kind_counts={},
        )

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not isinstance(ev, dict):
                continue
            total += 1
            payload = ev.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            action = str(payload.get("action") or "").strip()
            if action == "perception_snapshot":
                perception += 1
                snap = payload.get("snapshot") or {}
                if isinstance(snap, dict):
                    sit = snap.get("situation") or {}
                    if isinstance(sit, dict):
                        c = _safe_float(sit.get("confidence"))
                        if c is not None:
                            situation_confidences.append(c)
                    att = snap.get("attention") or {}
                    if isinstance(att, dict):
                        r = _safe_float(att.get("reduction_ratio"))
                        if r is not None:
                            attention_ratios.append(r)
                            attention_hits += 1
            elif action == "situation_to_skill_hit":
                reflex += 1
            elif action == "situation_to_skill_fail":
                reflex_fails += 1
            elif action == "capability_gap_detected":
                gaps += 1

            if str(ev.get("event_type") or "").strip().lower() == "planning":
                planning_events += 1
                ci = payload.get("context_injected") if isinstance(payload, dict) else None
                if isinstance(ci, dict):
                    g = _safe_float(ci.get("gist_memories_count"))
                    if g is not None:
                        gist_counts.append(g)
                        if g > 0:
                            gist_injected_events += 1

            # CognitiveLoop emits a SUMMARY event that carries aggregated metrics.
            if str(ev.get("event_type") or "").strip().lower() == "summary":
                metrics = payload.get("metrics") or {}
                if isinstance(metrics, dict):
                    r = _safe_float(metrics.get("prediction_error_rate"))
                    if r is not None:
                        pred_error_rates.append(r)
                    tc = _safe_float(metrics.get("tool_call_count"))
                    if tc is not None:
                        tool_call_counts.append(tc)
                    fr = _safe_float(metrics.get("fallback_to_planner_rate"))
                    if fr is not None:
                        fallback_rates.append(fr)
                    cm = _safe_float(metrics.get("context_misclass_rate"))
                    if cm is not None:
                        context_misclass_rates.append(cm)

            # EXECUTION events include raw step records; use them to count prediction_error types.
            if str(ev.get("event_type") or "").strip().lower() == "execution":
                raw = payload.get("raw") if isinstance(payload, dict) else None
                if isinstance(raw, dict):
                    steps = raw.get("steps") or []
                    if isinstance(steps, list):
                        for s in steps:
                            if not isinstance(s, dict):
                                continue
                            res = s.get("result")
                            if not isinstance(res, dict):
                                continue
                            meta = res.get("meta") if isinstance(res.get("meta"), dict) else {}
                            pe = meta.get("prediction_error") if isinstance(meta, dict) else None
                            if isinstance(pe, dict):
                                et = str(pe.get("error_type") or "").strip()
                                if et:
                                    pred_err_types[et] = int(pred_err_types.get(et, 0)) + 1

    attention_hit_rate = (attention_hits / perception) if perception > 0 else None
    gist_injection_rate = (gist_injected_events / planning_events) if planning_events > 0 else None
    top_types = sorted(pred_err_types.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    return Summary(
        trace_path=str(path),
        memory_db_path=None,
        total_events=total,
        planning_events=planning_events,
        perception_snapshots=perception,
        reflex_hits=reflex,
        reflex_fails=reflex_fails,
        capability_gaps=gaps,
        attention_reduction_avg=_avg(attention_ratios),
        attention_hit_rate=attention_hit_rate,
        situation_confidence_avg=_avg(situation_confidences),
        context_misclass_rate_avg=_avg(context_misclass_rates),
        prediction_error_rate_avg=_avg(pred_error_rates),
        tool_call_count_avg=_avg(tool_call_counts),
        fallback_to_planner_rate_avg=_avg(fallback_rates),
        top_prediction_error_types=top_types,
        gist_injection_rate=gist_injection_rate,
        gist_injected_avg_count=_avg([float(x) for x in gist_counts]),
        memory_kind_counts={},
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Summarize v3.1+ cognitive metrics from JSONL traces.")
    p.add_argument("--trace-path", default="data/traces/events.jsonl", help="Trace JSONL path (default: data/traces/events.jsonl)")
    p.add_argument("--memory-db", default="data/memory.db", help="Memory sqlite db path (default: data/memory.db)")
    p.add_argument("--json", action="store_true", help="Output JSON summary")
    args = p.parse_args()

    trace_path = Path(args.trace_path).resolve()
    if str(args.trace_path) == "data/traces/events.jsonl" and not trace_path.exists():
        # Keep CLI stable but honor QUENTIN_TRACES_DIR like JsonlTraceRecorder.
        trace_path = resolve_events_path(repo_root=".")
    summary = summarize_trace_file(trace_path)
    mem_db = Path(args.memory_db).resolve() if args.memory_db else None
    if mem_db is not None:
        summary.memory_db_path = str(mem_db)
        summary.memory_kind_counts = _memory_kind_counts(mem_db)
    if args.json:
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("==== Cognitive Metrics Summary (v3.1+) ====")
    print(f"Trace file                 : {summary.trace_path}")
    print(f"Total events               : {summary.total_events}")
    print(f"Planning events            : {summary.planning_events}")
    print(f"Perception snapshots       : {summary.perception_snapshots}")
    print(f"Reflex hits (situation->skill): {summary.reflex_hits}")
    print(f"Reflex fails               : {summary.reflex_fails}")
    print(f"Capability gaps detected   : {summary.capability_gaps}")
    if summary.reflex_hits:
        reflex_success = max(0, summary.reflex_hits - summary.reflex_fails)
        print(f"Reflex success rate        : {reflex_success / summary.reflex_hits:.3f}")
    if summary.situation_confidence_avg is not None:
        print(f"Avg situation confidence      : {summary.situation_confidence_avg:.3f}")
    if summary.attention_reduction_avg is not None:
        print(f"Avg attention reduction ratio : {summary.attention_reduction_avg:.3f}")
    if summary.attention_hit_rate is not None:
        print(f"Attention hit rate            : {summary.attention_hit_rate:.3f}")
    if summary.context_misclass_rate_avg is not None:
        print(f"Avg context_misclass_rate     : {summary.context_misclass_rate_avg:.3f}")
    if summary.prediction_error_rate_avg is not None:
        print(f"Avg prediction_error_rate     : {summary.prediction_error_rate_avg:.3f}")
    if summary.fallback_to_planner_rate_avg is not None:
        print(f"Avg fallback_to_planner_rate  : {summary.fallback_to_planner_rate_avg:.3f}")
    if summary.tool_call_count_avg is not None:
        print(f"Avg tool_call_count           : {summary.tool_call_count_avg:.2f}")
    if summary.gist_injection_rate is not None:
        print(f"Gist injection rate          : {summary.gist_injection_rate:.3f}")
    if summary.gist_injected_avg_count is not None:
        print(f"Avg gist injected count      : {summary.gist_injected_avg_count:.2f}")
    if summary.top_prediction_error_types:
        print("Top prediction_error types    :")
        for k, v in summary.top_prediction_error_types:
            print(f"  - {k}: {v}")
    if summary.memory_db_path:
        print(f"Memory DB                    : {summary.memory_db_path}")
    if summary.memory_kind_counts:
        print("Memory kind counts            :")
        for k in sorted(summary.memory_kind_counts.keys()):
            print(f"  - {k}: {summary.memory_kind_counts[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
