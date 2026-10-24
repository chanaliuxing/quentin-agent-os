from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psycopg
import pytest


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


def test_run_memory_slo_pipeline_supports_champion_backend(tmp_path: Path) -> None:
    dsn = _pg_dsn_from_env_or_default()
    qdrant_url = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").strip()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion slo pipeline test.")
    if not _qdrant_ready(qdrant_url):
        pytest.skip("Qdrant not ready for champion slo pipeline test.")

    repo_root = Path(__file__).resolve().parents[2]
    bench_out = tmp_path / "bench.champion.jsonl"
    slo_out = tmp_path / "slo.champion.generated.json"
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["QUENTIN_MEMORY_STORE"] = "champion"
    env["PG_DSN"] = dsn
    env["QDRANT_URL"] = qdrant_url
    env["MEM_EMBED_PROVIDER"] = "disabled"
    env["MEM_EMBED_DIM"] = "16"
    env["QUENTIN_QDRANT_WAIT_READY"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_memory_slo_pipeline.py"),
            "--backend",
            "champion",
            "--vector-backend",
            "qdrant",
            "--n",
            "60",
            "--tiers",
            "60",
            "--runs",
            "1",
            "--warmup",
            "0",
            "--dim",
            "16",
            "--top-k",
            "5",
            "--db-dir",
            str(db_dir),
            "--bench-out",
            str(bench_out),
            "--slo-in",
            "config/memory_recall_slo_champion.json",
            "--slo-out",
            str(slo_out),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert bench_out.exists()
    assert slo_out.exists()
