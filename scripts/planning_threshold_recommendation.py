from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_jsonl(path: Path, *, limit: int = 1000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    row = json.loads(s)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    if limit > 0 and len(rows) > limit:
        return rows[-limit:]
    return rows


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(float(v) for v in values)
    qq = max(0.0, min(1.0, float(q)))
    idx = int(round((len(xs) - 1) * qq))
    return float(xs[idx])


def _bucket_of(row: Dict[str, Any]) -> str:
    cb = row.get("calibration_bucket") if isinstance(row.get("calibration_bucket"), dict) else {}
    b = str(cb.get("domain") or row.get("domain_bucket") or "global").strip().lower()
    return b or "global"


def _extract_metric(row: Dict[str, Any], key: str) -> float | None:
    comps = row.get("score_components") if isinstance(row.get("score_components"), dict) else {}
    if key in comps:
        try:
            return float(comps.get(key))
        except Exception:
            return None
    if key == "attempt_band_coverage":
        ia = row.get("intelligence_audit") if isinstance(row.get("intelligence_audit"), dict) else {}
        strat = ia.get("strategy_regression") if isinstance(ia.get("strategy_regression"), dict) else {}
        switching = strat.get("strategy_switching") if isinstance(strat.get("strategy_switching"), dict) else {}
        try:
            return float(switching.get("attempt_band_coverage"))
        except Exception:
            return None
    return None


def recommend_thresholds(
    *,
    rows: List[Dict[str, Any]],
    min_samples: int = 8,
    quantile: float = 0.30,
    margins: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    metric_keys = [
        "strategy_switch_effectiveness",
        "interrupt_effectiveness",
        "reset_recovery_rate",
        "progress_sync_compliance",
        "attempt_band_coverage",
    ]
    clamps = {
        "strategy_switch_effectiveness": (0.40, 0.85),
        "interrupt_effectiveness": (0.35, 0.90),
        "reset_recovery_rate": (0.25, 0.85),
        "progress_sync_compliance": (0.60, 0.95),
        "attempt_band_coverage": (0.60, 0.95),
    }
    m = {
        "strategy_switch_effectiveness": 0.02,
        "interrupt_effectiveness": 0.03,
        "reset_recovery_rate": 0.03,
        "progress_sync_compliance": 0.03,
        "attempt_band_coverage": 0.02,
    }
    if isinstance(margins, dict):
        for k, v in margins.items():
            if k in m:
                try:
                    m[k] = float(v)
                except Exception:
                    pass

    by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_bucket.setdefault(_bucket_of(row), []).append(row)
    if "global" not in by_bucket:
        by_bucket["global"] = list(rows)

    out: Dict[str, Any] = {
        "generated_at": _now_utc_iso(),
        "sample_count": len(rows),
        "min_samples": int(min_samples),
        "quantile": float(quantile),
        "buckets": {},
    }

    global_rows = by_bucket.get("global") or []
    for bucket, bucket_rows in sorted(by_bucket.items()):
        use_rows = list(bucket_rows)
        fallback = False
        if bucket != "global" and len(bucket_rows) < min_samples and len(global_rows) >= min_samples:
            use_rows = list(global_rows)
            fallback = True
        metrics: Dict[str, Any] = {}
        for key in metric_keys:
            vals = []
            for r in use_rows:
                v = _extract_metric(r, key)
                if v is not None:
                    vals.append(v)
            if len(vals) < min_samples:
                continue
            base = _quantile(vals, quantile) - m[key]
            lo, hi = clamps[key]
            metrics[key] = max(lo, min(hi, float(base)))
        out["buckets"][bucket] = {
            "rows": len(bucket_rows),
            "used_rows": len(use_rows),
            "fallback_to_global": bool(fallback),
            "thresholds": metrics,
        }
    return out


def run(*, history: Path, output: Path, min_samples: int = 8, quantile: float = 0.30) -> Dict[str, Any]:
    rows = _read_jsonl(history, limit=5000)
    report = recommend_thresholds(rows=rows, min_samples=min_samples, quantile=quantile)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Generate recommended verify thresholds from planning benchmark history")
    p.add_argument("--history", default="generated/benchmarks/planning_process_benchmark_history.jsonl", help="History jsonl path")
    p.add_argument("--output", default="generated/benchmarks/planning_threshold_recommendation.json", help="Recommendation output path")
    p.add_argument("--min-samples", type=int, default=8)
    p.add_argument("--quantile", type=float, default=0.30)
    args = p.parse_args()

    report = run(
        history=Path(args.history),
        output=Path(args.output),
        min_samples=max(5, int(args.min_samples)),
        quantile=float(args.quantile),
    )
    print(json.dumps({
        "sample_count": report.get("sample_count"),
        "buckets": sorted(list((report.get("buckets") or {}).keys())),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
