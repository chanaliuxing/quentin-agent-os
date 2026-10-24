from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryRecord


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_git_head() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def _l2_norm(vec: list[float]) -> float:
    return sum(x * x for x in vec) ** 0.5


def _make_vector(i: int, *, dim: int, seed: int) -> list[float]:
    rng = random.Random((seed * 1_000_003) + i)
    vec = [rng.random() for _ in range(dim)]
    norm = _l2_norm(vec) or 1.0
    return [x / norm for x in vec]


def _make_code(i: int) -> str:
    # Bracketed code avoids substring false positives, e.g. "[CODE:E0010]" won't match "[CODE:E00100]".
    return f"[CODE:E{i:05d}]"


@dataclass(frozen=True)
class QueryCase:
    text_id: int
    vec_id: int

    @property
    def text_query(self) -> str:
        return _make_code(self.text_id)

    def vector(self, *, dim: int, seed: int) -> list[float]:
        return _make_vector(self.vec_id, dim=dim, seed=seed)


@dataclass
class BenchResult:
    ts_utc: str
    n_records: int
    mode: str
    backend: str
    store: str
    vector_backend: str
    vector_math_backend: str
    vector_fetch_strategy: str
    dim: int
    top_k: int
    runs: int
    warmup: int
    ingest_records_per_sec: float
    ingest_total_ms: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    hit_rate_at_k: float
    hit_rate_text_at_k: float
    hit_rate_vec_at_k: float
    python: str
    platform: str
    git_head: Optional[str] = None


def _load_slo_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _resolve_slo_rule(*, cfg: dict, n_records: int, mode: str) -> dict:
    if not isinstance(cfg, dict):
        return {}
    tiers = cfg.get("tiers")
    if not isinstance(tiers, dict):
        return {}
    n = int(n_records)
    available = []
    for k in tiers.keys():
        try:
            available.append(int(k))
        except Exception:
            continue
    if not available:
        return {}
    candidates = sorted(x for x in available if x <= n)
    tier_key = str(candidates[-1] if candidates else min(available))
    tier_cfg = tiers.get(tier_key) or {}
    if not isinstance(tier_cfg, dict):
        return {}
    modes = tier_cfg.get("modes") or {}
    if not isinstance(modes, dict):
        return {}
    rule = modes.get(str(mode)) or {}
    return rule if isinstance(rule, dict) else {}


def _evaluate_slo(results: list[BenchResult], cfg: dict) -> list[str]:
    violations: list[str] = []
    for r in results:
        rule = _resolve_slo_rule(cfg=cfg, n_records=int(r.n_records), mode=str(r.mode))
        if not rule:
            continue
        p95_max = rule.get("p95_ms_max")
        avg_max = rule.get("avg_ms_max")
        hit_min = rule.get("hit_rate_at_k_min")
        if p95_max is not None and float(r.p95_ms) > float(p95_max):
            violations.append(
                f"n={r.n_records} mode={r.mode} p95_ms={r.p95_ms:.3f} > max={float(p95_max):.3f}"
            )
        if avg_max is not None and float(r.avg_ms) > float(avg_max):
            violations.append(
                f"n={r.n_records} mode={r.mode} avg_ms={r.avg_ms:.3f} > max={float(avg_max):.3f}"
            )
        if hit_min is not None and float(r.hit_rate_at_k) < float(hit_min):
            violations.append(
                f"n={r.n_records} mode={r.mode} hit@k={r.hit_rate_at_k:.3f} < min={float(hit_min):.3f}"
            )
    return violations


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return float(values[0])
    k = (len(values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return float(values[f])
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return float(d0 + d1)


def _open_fabric(*, backend: str, db_path: Path) -> MemoryFabric:
    os.environ["MEM_EMBED_PROVIDER"] = "disabled"
    if backend == "sqlite_vec":
        os.environ["QUENTIN_MEMORY_STORE"] = "sqlite_vec"
    elif backend == "champion":
        os.environ["QUENTIN_MEMORY_STORE"] = "champion"
    else:
        os.environ["QUENTIN_MEMORY_STORE"] = "sqlite"
    return MemoryFabric(db_path=db_path)


def _populate(fabric: MemoryFabric, *, n: int, dim: int, seed: int) -> tuple[dict[int, str], float]:
    id_by_index: dict[int, str] = {}
    start = time.perf_counter()
    for i in range(n):
        text = f"{_make_code(i)} error occurred in subsystem {i % 5}"
        vec = _make_vector(i, dim=dim, seed=seed)
        rec = fabric.remember_atomic(content=text, source="bench", vector=vec)
        id_by_index[i] = rec.id
    ms = (time.perf_counter() - start) * 1000.0
    return id_by_index, ms


def _measure_one(fabric: MemoryFabric, query: MemoryQuery) -> tuple[list[MemoryRecord], float]:
    start = time.perf_counter()
    out = fabric.recall(query)
    ms = (time.perf_counter() - start) * 1000.0
    return out, ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory recall micro-benchmark (latency + hit@k).")
    parser.add_argument("--backend", default="sqlite", choices=["sqlite", "sqlite_vec", "champion"])
    parser.add_argument("--n", default="1000,10000", help="Comma-separated record counts (e.g. 1000,10000).")
    parser.add_argument("--modes", default="text_only,vector_only,hybrid", help="Comma-separated modes.")
    parser.add_argument("--dim", type=int, default=64, help="Vector dimension for synthetic embeddings.")
    parser.add_argument("--seed", type=int, default=13, help="Synthetic vector seed.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--runs", type=int, default=10, help="Measured iterations per mode (each iter runs all cases).")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup iterations per mode (not measured).")
    parser.add_argument("--db-dir", default="data/bench", help="Directory for temporary bench DB files.")
    parser.add_argument("--out", default="data/bench/recall_bench.jsonl", help="Output JSONL (ignored by git).")
    parser.add_argument(
        "--slo-file",
        default="config/memory_recall_slo.json",
        help="Optional SLO JSON config path for benchmark assertions.",
    )
    parser.add_argument(
        "--fail-on-slo",
        action="store_true",
        help="Exit non-zero when SLO violations are found.",
    )
    parser.add_argument(
        "--require-index-backend",
        action="store_true",
        help="Exit non-zero when requested index backend is not active (e.g. sqlite_vec fallback).",
    )
    args = parser.parse_args()

    ns = [int(x.strip()) for x in str(args.n).split(",") if x.strip()]
    modes = [m.strip() for m in str(args.modes).split(",") if m.strip()]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _cases_for_n(n: int) -> list[QueryCase]:
        """
        Pick stable in-range query cases for any dataset size.

        Invariants:
        - text_id and vec_id are always within [0, n-1]
        - Cases stay deterministic across runs for a given n
        """
        if n <= 1:
            return [QueryCase(text_id=0, vec_id=0)]
        ids = [
            min(10, n - 1),
            min(42, n - 1),
            min(max(0, n // 3), n - 1),
            min(max(0, n // 2), n - 1),
            n - 1,
        ]
        # Rotate vec ids to avoid identical (text_id == vec_id) for most cases.
        vec = ids[1:] + ids[:1]
        return [QueryCase(text_id=t, vec_id=v) for t, v in zip(ids, vec)]

    git_head = _maybe_git_head()
    py = f"{platform.python_implementation()} {platform.python_version()}"
    plat = f"{platform.system()} {platform.release()} ({platform.machine()})"

    results: list[BenchResult] = []

    for n in ns:
        cases = _cases_for_n(n)
        db_dir = Path(str(args.db_dir))
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"memory_bench_{args.backend}_{n}.db"
        if db_path.exists():
            db_path.unlink()

        fabric = _open_fabric(backend=args.backend, db_path=db_path)
        id_by_index, ingest_ms = _populate(fabric, n=n, dim=args.dim, seed=args.seed)
        ingest_rps = (float(n) / (ingest_ms / 1000.0)) if ingest_ms > 0 else 0.0
        stats = fabric.stats() if hasattr(fabric, "stats") else {}
        store = str(stats.get("store") or type(getattr(fabric, "store", object())).__name__)
        vec = stats.get("vector") if isinstance(stats, dict) else {}
        vector_backend = str((vec or {}).get("backend") or "unknown")
        vector_math_backend = str((vec or {}).get("math_backend") or "unknown")
        vector_fetch_strategy = str((vec or {}).get("fetch_strategy") or "unknown")
        if vector_backend.strip().lower() == "client_scan" and int(n) >= 10000:
            print(
                {
                    "issue": "vector_backend_client_scan",
                    "n": int(n),
                    "hint": "Install sqlite-vec (set QUENTIN_SQLITE_VEC_PATH) or use pgvector; otherwise vector recall scales poorly.",
                }
            )
        if vector_backend.strip().lower() == "client_scan" and vector_math_backend.strip().lower() == "python":
            print(
                {
                    "issue": "vector_math_python",
                    "n": int(n),
                    "hint": "Install numpy to accelerate client-scan cosine, or enable vector index backend.",
                }
            )
        if args.backend == "sqlite_vec" and vector_backend.strip().lower() != "sqlite_vec":
            print(
                {
                    "issue": "sqlite_vec_not_active",
                    "n": int(n),
                    "requested_backend": "sqlite_vec",
                    "actual_backend": vector_backend,
                    "hint": "sqlite-vec extension not loaded. Set QUENTIN_SQLITE_VEC_PATH to loadable sqlite-vec shared library.",
                }
            )
            if bool(args.require_index_backend):
                raise SystemExit(3)

        mode_summary: dict[str, dict[str, float]] = {}
        for mode in modes:
            latencies: list[float] = []
            hits_total = 0
            hits_text = 0
            hits_vec = 0
            attempts = 0

            def run_once_case(case: QueryCase) -> tuple[set[str], float]:
                q = MemoryQuery(
                    text=case.text_query,
                    vector=case.vector(dim=args.dim, seed=args.seed),
                    top_k=args.top_k,
                    mode=mode,
                    debug=False,
                )
                recs, ms = _measure_one(fabric, q)
                return {r.id for r in recs[: args.top_k]}, ms

            for _ in range(max(0, int(args.warmup))):
                for case in cases:
                    _ = run_once_case(case)

            for _ in range(max(1, int(args.runs))):
                for case in cases:
                    ids, ms = run_once_case(case)
                    latencies.append(ms)
                    attempts += 1

                    expected_text_id = id_by_index[case.text_id]
                    expected_vec_id = id_by_index[case.vec_id]

                    hit_text_case = expected_text_id in ids
                    hit_vec_case = expected_vec_id in ids

                    if mode == "text_only":
                        hits_total += int(hit_text_case)
                        hits_text += int(hit_text_case)
                    elif mode == "vector_only":
                        hits_total += int(hit_vec_case)
                        hits_vec += int(hit_vec_case)
                    else:
                        hits_total += int(hit_text_case and hit_vec_case)
                        hits_text += int(hit_text_case)
                        hits_vec += int(hit_vec_case)

            avg_ms = float(statistics.fmean(latencies)) if latencies else 0.0
            p50 = _percentile(latencies, 50.0)
            p95 = _percentile(latencies, 95.0)
            hit_rate = (hits_total / attempts) if attempts else 0.0
            hit_rate_text = (hits_text / attempts) if attempts else 0.0
            hit_rate_vec = (hits_vec / attempts) if attempts else 0.0
            mode_summary[str(mode)] = {
                "hit_rate_at_k": float(hit_rate),
                "hit_rate_text_at_k": float(hit_rate_text),
                "hit_rate_vec_at_k": float(hit_rate_vec),
            }

            results.append(
                BenchResult(
                    ts_utc=_now_utc_iso(),
                    n_records=n,
                    mode=mode,
                    backend=args.backend,
                    store=store,
                    vector_backend=vector_backend,
                    vector_math_backend=vector_math_backend,
                    vector_fetch_strategy=vector_fetch_strategy,
                    dim=int(args.dim),
                    top_k=int(args.top_k),
                    runs=int(args.runs),
                    warmup=int(args.warmup),
                    ingest_records_per_sec=float(ingest_rps),
                    ingest_total_ms=float(ingest_ms),
                    avg_ms=avg_ms,
                    p50_ms=p50,
                    p95_ms=p95,
                    hit_rate_at_k=float(hit_rate),
                    hit_rate_text_at_k=float(hit_rate_text),
                    hit_rate_vec_at_k=float(hit_rate_vec),
                    python=py,
                    platform=plat,
                    git_head=git_head,
                )
            )

        text_only_hit = float((mode_summary.get("text_only") or {}).get("hit_rate_at_k") or 0.0)
        hybrid_text_hit = float((mode_summary.get("hybrid") or {}).get("hit_rate_text_at_k") or 0.0)
        if text_only_hit >= 0.9 and hybrid_text_hit < 0.5 and "hybrid" in mode_summary:
            print(
                {
                    "issue": "hybrid_keyword_starvation",
                    "n": int(n),
                    "text_only_hit": round(text_only_hit, 3),
                    "hybrid_text_hit": round(hybrid_text_hit, 3),
                    "hint": "Check hybrid fusion weights/anchor policy; ensure exact keyword hits are preserved.",
                }
            )

    with out_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    print("Bench results (written to:", str(out_path) + ")")
    for r in results:
        print(
            {
                "n": r.n_records,
                "mode": r.mode,
                "backend": r.backend,
                "vector_backend": r.vector_backend,
                "vector_fetch_strategy": r.vector_fetch_strategy,
                "avg_ms": round(r.avg_ms, 3),
                "p95_ms": round(r.p95_ms, 3),
                "hit@k": round(r.hit_rate_at_k, 3),
                "hit_text@k": round(r.hit_rate_text_at_k, 3),
                "hit_vec@k": round(r.hit_rate_vec_at_k, 3),
            }
        )

    slo_cfg = _load_slo_config(str(args.slo_file))
    if slo_cfg:
        violations = _evaluate_slo(results, slo_cfg)
        if violations:
            print("SLO violations:")
            for v in violations:
                print({"violation": v})
            if bool(args.fail_on_slo):
                raise SystemExit(2)
        else:
            print("SLO check: PASS")


if __name__ == "__main__":
    main()
