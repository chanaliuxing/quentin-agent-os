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
from quentin.memory.models import MemoryQuery, MemoryRecord, MemoryTier


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


@dataclass(frozen=True)
class TaskCase:
    idx: int
    domain: str
    query_kind: str
    expected_token: str
    query_text: str
    expected_record_id: str


@dataclass
class IntelligenceBenchResult:
    ts_utc: str
    n_records: int
    n_cases: int
    case_profile: str
    query_domain_policy: str
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
    avg_ms: float
    p95_ms: float
    task_success_rate: float
    first_hit_useful_rate: float
    error_recurrence_rate: float
    memory_pollution_rate: float
    intelligence_score: float
    python: str
    platform: str
    git_head: Optional[str] = None


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _open_fabric(*, backend: str, db_path: Path) -> MemoryFabric:
    os.environ["MEM_EMBED_PROVIDER"] = "disabled"
    # Hybrid benchmarks are otherwise dominated by LIKE scans at scale.
    os.environ.setdefault("QUENTIN_MEMORY_FTS", "1")
    if backend == "champion":
        os.environ["QUENTIN_MEMORY_STORE"] = "champion"
        # Default to local docker compose settings
        os.environ.setdefault("PG_HOST", "localhost")
        os.environ.setdefault("PG_PORT", "55432")
        os.environ.setdefault("PG_USER", "postgres")
        os.environ.setdefault("PG_PASSWORD", "postgres")
        os.environ.setdefault("PG_DB", "quentin_memory")
        os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
        return MemoryFabric(db_path=db_path)
    os.environ["QUENTIN_MEMORY_STORE"] = "sqlite_vec" if backend == "sqlite_vec" else "sqlite"
    return MemoryFabric(db_path=db_path)


def _populate_corpus(
    fabric: MemoryFabric,
    *,
    n: int,
    n_cases: int,
    dim: int,
    seed: int,
    case_profile: str,
) -> tuple[list[TaskCase], float]:
    domains = ["auth", "payments", "search", "planner", "memory"]
    start = time.perf_counter()
    expected: list[TaskCase] = []

    store = getattr(fabric, "store", None)
    store_name = type(store).__name__ if store is not None else ""
    can_batch = bool(getattr(store, "add_many", None)) and store_name in ("ChampionMemoryStore",)
    batch: list[MemoryRecord] = []

    def _flush() -> None:
        nonlocal batch
        if not batch:
            return
        if can_batch:
            store.add_many(batch)  # type: ignore[union-attr]
        else:
            for r in batch:
                fabric.store.add(r)
        batch = []

    try:
        batch_size = int(os.getenv("QUENTIN_BENCH_INGEST_BATCH", "2000") or 2000)
    except Exception:
        batch_size = 2000
    batch_size = max(1, min(50_000, int(batch_size)))

    for i in range(n):
        domain = domains[i % len(domains)]
        token = f"[CASE:{i:05d}]"
        content = f"[DOMAIN:{domain}] {token} incident in module {domain} case-id {i} root-cause signature {i % 11}"
        rec = MemoryRecord.new(
            tier=MemoryTier.STS,
            content=content,
            source="intelligence_bench",
            domain=domain,
            vector=_make_vector(i, dim=dim, seed=seed),
            metadata={"domain": domain, "kind": "signal"},
        )
        batch.append(rec)
        if len(expected) < n_cases and (i % max(1, (n // max(1, n_cases)))) == 0:
            query_kind = "exact"
            query_text = token
            if str(case_profile) == "mixed" and (len(expected) % 2 == 1):
                query_kind = "semantic"
                query_text = f"{domain} module incident case-id {i} signature"
            expected.append(
                TaskCase(
                    idx=i,
                    domain=domain,
                    query_kind=query_kind,
                    expected_token=token,
                    query_text=query_text,
                    expected_record_id=rec.id,
                )
            )
        if len(batch) >= batch_size:
            _flush()
    _flush()

    # Add noise records to test pollution resistance.
    try:
        noise_ratio = float(os.getenv("QUENTIN_BENCH_NOISE_RATIO", "0.10") or 0.10)
    except Exception:
        noise_ratio = 0.10
    noise_ratio = max(0.0, min(1.0, float(noise_ratio)))
    noise_n = max(0, int(n * noise_ratio))
    if noise_n <= 0 and n > 0:
        noise_n = 1
    for i in range(noise_n):
        token = f"[NOISE:{i:05d}]"
        content = f"[DOMAIN:noise] {token} irrelevant chatter random note {i}"
        rec = MemoryRecord.new(
            tier=MemoryTier.STS,
            content=content,
            source="intelligence_bench",
            domain="noise",
            vector=_make_vector(n + i, dim=dim, seed=seed + 17),
            metadata={"domain": "noise", "kind": "noise"},
        )
        batch.append(rec)
        if len(batch) >= batch_size:
            _flush()
    _flush()

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return expected[:n_cases], elapsed_ms


def _measure_one(fabric: MemoryFabric, query: MemoryQuery) -> tuple[list[MemoryRecord], float]:
    t0 = time.perf_counter()
    out = fabric.recall(query)
    return out, (time.perf_counter() - t0) * 1000.0


def _is_useful(record: MemoryRecord, case: TaskCase) -> bool:
    content = str(getattr(record, "content", "") or "")
    return record.id == case.expected_record_id or (case.expected_token in content and f"[DOMAIN:{case.domain}]" in content)


def _is_polluted(record: MemoryRecord, case: TaskCase) -> bool:
    content = str(getattr(record, "content", "") or "")
    if _is_useful(record, case):
        return False
    return f"[DOMAIN:{case.domain}]" not in content


def _weights(cfg: dict) -> dict[str, float]:
    raw = (cfg or {}).get("weights") if isinstance(cfg, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    w = {
        "task_success_rate": float(raw.get("task_success_rate", 0.45)),
        "first_hit_useful_rate": float(raw.get("first_hit_useful_rate", 0.25)),
        "error_recurrence_resistance": float(raw.get("error_recurrence_resistance", 0.20)),
        "memory_pollution_resistance": float(raw.get("memory_pollution_resistance", 0.10)),
    }
    s = sum(max(0.0, v) for v in w.values()) or 1.0
    return {k: max(0.0, v) / s for k, v in w.items()}


def _score(
    *,
    task_success_rate: float,
    first_hit_useful_rate: float,
    error_recurrence_rate: float,
    memory_pollution_rate: float,
    cfg: dict,
) -> float:
    w = _weights(cfg)
    val = (
        task_success_rate * w["task_success_rate"]
        + first_hit_useful_rate * w["first_hit_useful_rate"]
        + max(0.0, 1.0 - error_recurrence_rate) * w["error_recurrence_resistance"]
        + max(0.0, 1.0 - memory_pollution_rate) * w["memory_pollution_resistance"]
    )
    return round(100.0 * max(0.0, min(1.0, val)), 3)


def _thresholds(cfg: dict) -> dict[str, float]:
    raw = (cfg or {}).get("thresholds") if isinstance(cfg, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "task_success_rate_min": float(raw.get("task_success_rate_min", 0.85)),
        "first_hit_useful_rate_min": float(raw.get("first_hit_useful_rate_min", 0.75)),
        "error_recurrence_rate_max": float(raw.get("error_recurrence_rate_max", 0.20)),
        "memory_pollution_rate_max": float(raw.get("memory_pollution_rate_max", 0.35)),
        "intelligence_score_min": float(raw.get("intelligence_score_min", 75.0)),
        "p95_ms_max": float(raw.get("p95_ms_max", 800.0)),
    }


def _evaluate_slo(results: list[IntelligenceBenchResult], cfg: dict) -> list[str]:
    t = _thresholds(cfg)
    out: list[str] = []
    for r in results:
        if r.task_success_rate < t["task_success_rate_min"]:
            out.append(f"n={r.n_records} mode={r.mode} task_success_rate={r.task_success_rate:.3f} < min={t['task_success_rate_min']:.3f}")
        if r.first_hit_useful_rate < t["first_hit_useful_rate_min"]:
            out.append(f"n={r.n_records} mode={r.mode} first_hit_useful_rate={r.first_hit_useful_rate:.3f} < min={t['first_hit_useful_rate_min']:.3f}")
        if r.error_recurrence_rate > t["error_recurrence_rate_max"]:
            out.append(f"n={r.n_records} mode={r.mode} error_recurrence_rate={r.error_recurrence_rate:.3f} > max={t['error_recurrence_rate_max']:.3f}")
        if r.memory_pollution_rate > t["memory_pollution_rate_max"]:
            out.append(f"n={r.n_records} mode={r.mode} memory_pollution_rate={r.memory_pollution_rate:.3f} > max={t['memory_pollution_rate_max']:.3f}")
        if r.intelligence_score < t["intelligence_score_min"]:
            out.append(f"n={r.n_records} mode={r.mode} intelligence_score={r.intelligence_score:.3f} < min={t['intelligence_score_min']:.3f}")
        if r.p95_ms > t["p95_ms_max"]:
            out.append(f"n={r.n_records} mode={r.mode} p95_ms={r.p95_ms:.3f} > max={t['p95_ms_max']:.3f}")
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if len(vs) == 1:
        return float(vs[0])
    k = (len(vs) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    if f == c:
        return float(vs[f])
    return float(vs[f] * (c - k) + vs[c] * (k - f))


def main() -> None:
    p = argparse.ArgumentParser(description="Memory intelligence benchmark (quality-first, latency-constrained).")
    p.add_argument("--backend", default="sqlite", choices=["sqlite", "sqlite_vec", "champion"])
    p.add_argument("--n", default="1000,10000", help="Comma-separated corpus sizes")
    p.add_argument("--modes", default="text_only,vector_only,hybrid")
    p.add_argument(
        "--case-profile",
        default="mixed",
        choices=["basic", "mixed"],
        help="Case difficulty profile: basic (exact tokens) or mixed (exact + semantic).",
    )
    p.add_argument("--cases", type=int, default=40, help="Task cases per dataset size")
    p.add_argument("--dim", type=int, default=768)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument(
        "--query-domain-policy",
        default="case",
        choices=["none", "case"],
        help="Whether to include case domain in recall query.",
    )
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--db-dir", default="data/bench")
    p.add_argument("--out", default="data/bench/memory_intelligence_bench.jsonl")
    p.add_argument("--slo-file", default="config/memory_intelligence_slo.json")
    p.add_argument("--fail-on-slo", action="store_true")
    p.add_argument("--require-index-backend", action="store_true")
    p.add_argument("--champion-cleanup", action="store_true", help="Cleanup champion namespace after each mode.")
    p.add_argument(
        "--champion-drop-collection",
        action="store_true",
        help="When used with --champion-cleanup, also drop Qdrant collection for this run namespace.",
    )
    args = p.parse_args()
    # Ensure synthetic vectors match the configured store dimension.
    os.environ["MEM_EMBED_DIM"] = str(int(args.dim))
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"

    ns = [int(x.strip()) for x in str(args.n).split(",") if x.strip()]
    modes = [x.strip() for x in str(args.modes).split(",") if x.strip()]

    out_path = Path(str(args.out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = _load_json(str(args.slo_file))

    py = f"{platform.python_implementation()} {platform.python_version()}"
    plat = f"{platform.system()} {platform.release()} ({platform.machine()})"
    git_head = _maybe_git_head()

    results: list[IntelligenceBenchResult] = []

    for n in ns:
        for mode in modes:
            # Isolate datasets when using shared external backends (Postgres/Qdrant).
            os.environ["QUENTIN_MEMORY_NAMESPACE"] = f"bench_{args.backend}_{n}_{mode}_{run_tag}"
            db_dir = Path(str(args.db_dir))
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"memory_intelligence_{args.backend}_{n}_{mode}.db"
            if db_path.exists():
                db_path.unlink()

            fabric = _open_fabric(backend=str(args.backend), db_path=db_path)
            cases, _ingest_ms = _populate_corpus(
                fabric,
                n=int(n),
                n_cases=max(1, int(args.cases)),
                dim=int(args.dim),
                seed=int(args.seed),
                case_profile=str(args.case_profile),
            )

            stats = fabric.stats() if hasattr(fabric, "stats") else {}
            store = str(stats.get("store") or type(getattr(fabric, "store", object())).__name__)
            vec = stats.get("vector") if isinstance(stats, dict) else {}
            vector_backend = str((vec or {}).get("backend") or "unknown")
            vector_math_backend = str((vec or {}).get("math_backend") or "unknown")
            vector_fetch_strategy = str((vec or {}).get("fetch_strategy") or "unknown")

            if args.backend == "sqlite_vec" and vector_backend.strip().lower() != "sqlite_vec":
                print(
                    {
                        "issue": "sqlite_vec_not_active",
                        "n": int(n),
                        "mode": str(mode),
                        "requested_backend": "sqlite_vec",
                        "actual_backend": vector_backend,
                        "hint": "sqlite-vec extension not loaded. Set QUENTIN_SQLITE_VEC_PATH or install sqlite-vec python package in active venv.",
                    }
                )
                if bool(args.require_index_backend):
                    raise SystemExit(3)

            latencies: list[float] = []
            success_cnt = 0
            first_hit_cnt = 0
            polluted_items = 0
            returned_items = 0
            failed_cases: list[TaskCase] = []

            def _query(case: TaskCase) -> tuple[list[MemoryRecord], float]:
                q_domain = case.domain if str(args.query_domain_policy) == "case" else None
                q = MemoryQuery(
                    text=case.query_text,
                    vector=_make_vector(case.idx, dim=int(args.dim), seed=int(args.seed)),
                    top_k=int(args.top_k),
                    mode=str(mode),
                    domain=q_domain,
                    include_cross_domain=False,
                    debug=False,
                )
                return _measure_one(fabric, q)

            for _ in range(max(0, int(args.warmup))):
                for c in cases:
                    _ = _query(c)

            for _ in range(max(1, int(args.runs))):
                for c in cases:
                    recs, ms = _query(c)
                    latencies.append(ms)
                    top = recs[: int(args.top_k)]

                    useful_any = any(_is_useful(r, c) for r in top)
                    useful_top1 = bool(top) and _is_useful(top[0], c)

                    success_cnt += int(useful_any)
                    first_hit_cnt += int(useful_top1)
                    if not useful_any:
                        failed_cases.append(c)

                    for r in top:
                        returned_items += 1
                        polluted_items += int(_is_polluted(r, c))

            # Learning loop: inject correction for failed cases and re-check first hit quality.
            remaining_fail = 0
            unique_failed = {(c.idx, c.domain, c.expected_token): c for c in failed_cases}
            for c in unique_failed.values():
                correction = (
                    f"[DOMAIN:{c.domain}] {c.expected_token} "
                    f"correction anchor {c.query_text} verified resolution"
                )
                fabric.remember_atomic(
                    content=correction,
                    source="intelligence_bench_feedback",
                    domain=c.domain,
                    vector=_make_vector(c.idx, dim=int(args.dim), seed=int(args.seed)),
                    metadata={"domain": c.domain, "kind": "correction"},
                )
                recs2, _ = _query(c)
                top2 = recs2[: int(args.top_k)]
                if not any(_is_useful(r, c) for r in top2):
                    remaining_fail += 1

            attempts = max(1, len(cases) * max(1, int(args.runs)))
            task_success_rate = success_cnt / attempts
            first_hit_useful_rate = first_hit_cnt / attempts
            error_recurrence_rate = (
                remaining_fail / len(unique_failed) if unique_failed else 0.0
            )
            memory_pollution_rate = polluted_items / returned_items if returned_items else 0.0
            score = _score(
                task_success_rate=task_success_rate,
                first_hit_useful_rate=first_hit_useful_rate,
                error_recurrence_rate=error_recurrence_rate,
                memory_pollution_rate=memory_pollution_rate,
                cfg=cfg,
            )

            avg_ms = float(statistics.fmean(latencies)) if latencies else 0.0
            p95_ms = _percentile(latencies, 95.0)

            if task_success_rate < 0.7:
                print({"issue": "task_success_low", "n": n, "mode": mode, "value": round(task_success_rate, 3)})
            if first_hit_useful_rate < 0.6:
                print({"issue": "first_hit_useful_low", "n": n, "mode": mode, "value": round(first_hit_useful_rate, 3)})
            if error_recurrence_rate > 0.3:
                print({"issue": "error_recurrence_high", "n": n, "mode": mode, "value": round(error_recurrence_rate, 3)})
            if memory_pollution_rate > 0.4:
                print({"issue": "memory_pollution_high", "n": n, "mode": mode, "value": round(memory_pollution_rate, 3)})

            results.append(
                IntelligenceBenchResult(
                    ts_utc=_now_utc_iso(),
                    n_records=int(n),
                    n_cases=len(cases),
                    case_profile=str(args.case_profile),
                    query_domain_policy=str(args.query_domain_policy),
                    mode=str(mode),
                    backend=str(args.backend),
                    store=store,
                    vector_backend=vector_backend,
                    vector_math_backend=vector_math_backend,
                    vector_fetch_strategy=vector_fetch_strategy,
                    dim=int(args.dim),
                    top_k=int(args.top_k),
                    runs=int(args.runs),
                    warmup=int(args.warmup),
                    avg_ms=float(avg_ms),
                    p95_ms=float(p95_ms),
                    task_success_rate=float(task_success_rate),
                    first_hit_useful_rate=float(first_hit_useful_rate),
                    error_recurrence_rate=float(error_recurrence_rate),
                    memory_pollution_rate=float(memory_pollution_rate),
                    intelligence_score=float(score),
                    python=py,
                    platform=plat,
                    git_head=git_head,
                )
            )

            if str(args.backend) == "champion" and bool(args.champion_cleanup):
                try:
                    store = getattr(fabric, "store", None)
                    if hasattr(store, "cleanup_namespace"):
                        cleanup_info = store.cleanup_namespace(drop_collection=bool(args.champion_drop_collection))
                        print({"champion_cleanup": cleanup_info})
                except Exception as e:
                    print({"issue": "champion_cleanup_failed", "error": str(e)})

    with out_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    print("Intelligence bench results (written to:", str(out_path) + ")")
    for r in results:
        print(
            {
                "n": r.n_records,
                "mode": r.mode,
                "backend": r.backend,
                "vector_backend": r.vector_backend,
                "avg_ms": round(r.avg_ms, 3),
                "p95_ms": round(r.p95_ms, 3),
                "task_success_rate": round(r.task_success_rate, 3),
                "first_hit_useful_rate": round(r.first_hit_useful_rate, 3),
                "error_recurrence_rate": round(r.error_recurrence_rate, 3),
                "memory_pollution_rate": round(r.memory_pollution_rate, 3),
                "intelligence_score": round(r.intelligence_score, 3),
            }
        )

    violations = _evaluate_slo(results, cfg) if cfg else []
    if violations:
        print("Intelligence SLO violations:")
        for v in violations:
            print({"violation": v})
        if bool(args.fail_on_slo):
            raise SystemExit(2)
    elif cfg:
        print("Intelligence SLO check: PASS")


if __name__ == "__main__":
    main()
