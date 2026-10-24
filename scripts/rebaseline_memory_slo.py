from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _pick_latest(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: str(r.get("ts_utc") or ""))
    return rows[-1]


def build_slo(
    *,
    rows: List[Dict[str, Any]],
    tiers: List[int],
    mode_list: List[str],
    backend_filter: Optional[str],
    vector_backend_filter: Optional[str],
    p95_factor: float,
    avg_factor: float,
    hit_margin: float,
) -> Tuple[Dict[str, Any], int]:
    filtered = []
    for row in rows:
        if backend_filter and str(row.get("backend") or "") != backend_filter:
            continue
        if vector_backend_filter and str(row.get("vector_backend") or "") != vector_backend_filter:
            continue
        filtered.append(row)

    out: Dict[str, Any] = {"tiers": {}}
    for tier in tiers:
        mode_cfg: Dict[str, Any] = {}
        for mode in mode_list:
            candidates = [
                r
                for r in filtered
                if _safe_int(r.get("n_records"), -1) == int(tier) and str(r.get("mode") or "") == mode
            ]
            latest = _pick_latest(candidates)
            if latest is None:
                continue
            p95 = _safe_float(latest.get("p95_ms"), 0.0)
            avg = _safe_float(latest.get("avg_ms"), 0.0)
            hit = _safe_float(latest.get("hit_rate_at_k"), 0.0)
            mode_cfg[mode] = {
                "p95_ms_max": round(max(1.0, p95 * p95_factor), 3),
                "avg_ms_max": round(max(1.0, avg * avg_factor), 3),
                "hit_rate_at_k_min": round(max(0.0, min(1.0, hit - hit_margin)), 3),
            }
        if mode_cfg:
            out["tiers"][str(tier)] = {"modes": mode_cfg}
    return out, len(filtered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build memory recall SLO config from benchmark JSONL.")
    parser.add_argument("--in", dest="input_path", default="data/bench/recall_bench.jsonl")
    parser.add_argument("--out", dest="output_path", default="config/memory_recall_slo.generated.json")
    parser.add_argument("--tiers", default="10000,100000,1000000")
    parser.add_argument("--modes", default="text_only,vector_only,hybrid")
    parser.add_argument("--backend", default="", help="Filter benchmark rows by backend value.")
    parser.add_argument("--vector-backend", default="", help="Filter rows by vector_backend (e.g. sqlite_vec).")
    parser.add_argument("--p95-factor", type=float, default=1.25)
    parser.add_argument("--avg-factor", type=float, default=1.2)
    parser.add_argument("--hit-margin", type=float, default=0.03)
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit non-zero when no tiers are generated after filtering.",
    )
    args = parser.parse_args()

    input_path = Path(str(args.input_path))
    rows = _read_jsonl(input_path)
    tiers = [_safe_int(x.strip(), 0) for x in str(args.tiers).split(",") if x.strip()]
    tiers = [x for x in tiers if x > 0]
    modes = [m.strip() for m in str(args.modes).split(",") if m.strip()]
    backend_filter = str(args.backend or "").strip() or None
    vector_backend_filter = str(args.vector_backend or "").strip() or None

    result, filtered_rows = build_slo(
        rows=rows,
        tiers=tiers,
        mode_list=modes,
        backend_filter=backend_filter,
        vector_backend_filter=vector_backend_filter,
        p95_factor=float(args.p95_factor),
        avg_factor=float(args.avg_factor),
        hit_margin=float(args.hit_margin),
    )
    out_path = Path(str(args.output_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_tiers = len((result.get("tiers") or {}))
    print(
        {
            "input_rows": len(rows),
            "filtered_rows": int(filtered_rows),
            "output_tiers": int(output_tiers),
            "output_path": str(out_path),
            "backend_filter": backend_filter,
            "vector_backend_filter": vector_backend_filter,
        }
    )
    if bool(args.fail_on_empty) and output_tiers == 0:
        raise SystemExit(4)


if __name__ == "__main__":
    main()
