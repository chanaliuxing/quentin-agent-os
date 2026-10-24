from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import URLError
from urllib.request import urlopen

import psycopg

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryRecord, MemoryTier


def _pg_dsn_from_env_or_default() -> str:
    dsn = (os.getenv("PG_DSN") or "").strip()
    if dsn:
        return dsn
    host = (os.getenv("PG_HOST") or "127.0.0.1").strip()
    port = (os.getenv("PG_PORT") or "55432").strip()
    user = (os.getenv("PG_USER") or "postgres").strip()
    password = os.getenv("PG_PASSWORD", "postgres")
    db = (os.getenv("PG_DB") or "quentin_memory").strip()
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _pg_ready(dsn: str) -> bool:
    try:
        conn = psycopg.connect(dsn, connect_timeout=2)
        try:
            row = conn.execute("SELECT 1").fetchone()
            return bool(row)
        finally:
            conn.close()
    except Exception:
        return False


def _qdrant_ready(url: str) -> bool:
    target = f"{url.rstrip('/')}/readyz"
    try:
        with urlopen(target, timeout=1.2) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (URLError, TimeoutError, OSError):
        return False


def _l2_norm(vec: List[float]) -> float:
    return sum(x * x for x in vec) ** 0.5


def _make_vector(i: int, *, dim: int, seed: int) -> List[float]:
    rng = random.Random((seed * 1_000_003) + i)
    raw = [rng.random() for _ in range(dim)]
    norm = _l2_norm(raw) or 1.0
    return [x / norm for x in raw]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    seq = sorted(values)
    if len(seq) == 1:
        return float(seq[0])
    k = (len(seq) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(seq) - 1)
    if f == c:
        return float(seq[f])
    return float(seq[f] * (c - k) + seq[c] * (k - f))


def _build_records(n: int, *, dim: int, seed: int) -> List[MemoryRecord]:
    out: List[MemoryRecord] = []
    for i in range(n):
        code = f"[SCALE:{i:05d}]"
        out.append(
            MemoryRecord.new(
                tier=MemoryTier.STS,
                content=f"{code} champion scale memory {i}",
                source="champion_scale_bench",
                domain="core",
                vector=_make_vector(i, dim=dim, seed=seed),
                metadata={"scale_id": i},
            )
        )
    return out


def _query_chunk(repo_root: Path, indices: List[int], *, dim: int, seed: int, top_k: int) -> Tuple[int, List[float]]:
    fabric = MemoryFabric(repo_root=repo_root)
    hits = 0
    latencies: List[float] = []
    for idx in indices:
        start = time.perf_counter()
        out = fabric.recall(MemoryQuery(vector=_make_vector(idx, dim=dim, seed=seed), mode="vector_only", top_k=top_k))
        latencies.append((time.perf_counter() - start) * 1000.0)
        token = f"[SCALE:{idx:05d}]"
        if any(token in (r.content or "") for r in out):
            hits += 1
    return hits, latencies


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Champion/Qdrant scale e2e benchmark with acceptance gates.")
    p.add_argument("--n-records", type=int, default=2000)
    p.add_argument("--queries", type=int, default=200)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--dim", type=int, default=16)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--ingest-batch", type=int, default=500)
    p.add_argument("--qdrant-wait-s", type=float, default=1.5)
    p.add_argument("--min-hit-rate", type=float, default=0.95)
    p.add_argument("--p95-ms-max", type=float, default=800.0)
    p.add_argument("--require-qdrant-ready", action="store_true")
    p.add_argument("--expect-vec-ready", type=int, choices=[0, 1], default=-1)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dsn = _pg_dsn_from_env_or_default()
    qdrant_url = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").strip()
    if not _pg_ready(dsn):
        print(json.dumps({"status": "skip", "reason": "postgres_not_ready"}))
        return 2
    q_ready = _qdrant_ready(qdrant_url)
    if args.require_qdrant_ready and (not q_ready):
        print(json.dumps({"status": "skip", "reason": "qdrant_not_ready", "qdrant_url": qdrant_url}))
        return 3

    namespace = f"scale_{uuid.uuid4().hex[:10]}"
    os.environ["QUENTIN_MEMORY_STORE"] = "champion"
    os.environ["PG_DSN"] = dsn
    os.environ["QDRANT_URL"] = qdrant_url
    os.environ["QUENTIN_MEMORY_NAMESPACE"] = namespace
    os.environ["MEM_EMBED_PROVIDER"] = "disabled"
    os.environ["MEM_EMBED_DIM"] = str(int(args.dim))
    os.environ.setdefault("QUENTIN_QDRANT_WAIT_READY", "1")

    fabric = MemoryFabric(repo_root=repo_root)
    store = fabric.store
    if args.expect_vec_ready in (0, 1):
        vec_ready = bool(getattr(store, "_vec_ready", False))
        if vec_ready != bool(args.expect_vec_ready):
            print(
                json.dumps(
                    {
                        "status": "error",
                        "reason": "vec_ready_mismatch",
                        "expected": bool(args.expect_vec_ready),
                        "actual": vec_ready,
                    }
                )
            )
            return 4

    records = _build_records(int(args.n_records), dim=int(args.dim), seed=int(args.seed))
    ingest_start = time.perf_counter()
    batch = max(1, int(args.ingest_batch))
    for i in range(0, len(records), batch):
        store.add_many(records[i : i + batch])
    ingest_ms = (time.perf_counter() - ingest_start) * 1000.0

    time.sleep(max(0.0, float(args.qdrant_wait_s)))

    # Query workers do not need readiness wait; avoid long retries on degraded path.
    os.environ["QUENTIN_QDRANT_WAIT_READY"] = "0"

    query_rng = random.Random(20260328)
    sample_indices = [query_rng.randrange(0, int(args.n_records)) for _ in range(int(args.queries))]

    latencies: List[float] = []
    hits = 0
    workers = max(1, int(args.workers))
    chunks: List[List[int]] = [[] for _ in range(workers)]
    for i, idx in enumerate(sample_indices):
        chunks[i % workers].append(idx)
    chunks = [c for c in chunks if c]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                _query_chunk,
                repo_root,
                chunk,
                dim=int(args.dim),
                seed=int(args.seed),
                top_k=int(args.top_k),
            )
            for chunk in chunks
        ]
        for fut in as_completed(futs):
            chunk_hits, chunk_latencies = fut.result()
            hits += int(chunk_hits)
            latencies.extend(float(x) for x in chunk_latencies)

    hit_rate = (hits / len(sample_indices)) if sample_indices else 0.0
    p95_ms = _percentile(latencies, 95.0)
    summary: Dict[str, Any] = {
        "status": "ok",
        "namespace": namespace,
        "n_records": int(args.n_records),
        "queries": int(args.queries),
        "workers": workers,
        "dim": int(args.dim),
        "top_k": int(args.top_k),
        "hit_rate": float(hit_rate),
        "p95_ms": float(p95_ms),
        "avg_ms": float(sum(latencies) / len(latencies)) if latencies else 0.0,
        "ingest_ms": float(ingest_ms),
        "vec_ready": bool(getattr(store, "_vec_ready", False)),
        "qdrant_ready_endpoint": bool(q_ready),
    }

    ok = True
    if float(hit_rate) < float(args.min_hit_rate):
        ok = False
        summary["gate_fail"] = f"hit_rate<{float(args.min_hit_rate):.3f}"
    if float(p95_ms) > float(args.p95_ms_max):
        ok = False
        summary["gate_fail"] = f"p95_ms>{float(args.p95_ms_max):.3f}"

    print(json.dumps(summary, ensure_ascii=False))

    try:
        if hasattr(store, "cleanup_namespace"):
            store.cleanup_namespace(drop_collection=True)
    except Exception:
        pass
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
