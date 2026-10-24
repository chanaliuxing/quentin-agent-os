from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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


def test_champion_scale_e2e_qdrant_ready_profile_runs() -> None:
    dsn = _pg_dsn_from_env_or_default()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion scale ready-path test.")

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PG_DSN"] = dsn
    env["QDRANT_URL"] = (env.get("QDRANT_URL") or "http://127.0.0.1:6333").strip()
    env["QUENTIN_CHAMPION_STORE_VECTORS_IN_PG"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_memory_champion_scale.py"),
            "--n-records",
            "600",
            "--queries",
            "80",
            "--workers",
            "8",
            "--dim",
            "16",
            "--top-k",
            "10",
            "--min-hit-rate",
            "0.90",
            "--p95-ms-max",
            "1500",
            "--require-qdrant-ready",
            "--expect-vec-ready",
            "1",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode in (2, 3):
        pytest.skip(proc.stdout[-1200:] + proc.stderr[-1200:])
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]


def test_champion_scale_e2e_fallback_profile_runs() -> None:
    dsn = _pg_dsn_from_env_or_default()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion scale fallback-path test.")

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PG_DSN"] = dsn
    env["QDRANT_URL"] = "http://127.0.0.1:1"
    env["QUENTIN_CHAMPION_STORE_VECTORS_IN_PG"] = "1"
    env["QUENTIN_QDRANT_WAIT_READY"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_memory_champion_scale.py"),
            "--n-records",
            "200",
            "--queries",
            "24",
            "--workers",
            "3",
            "--dim",
            "16",
            "--top-k",
            "10",
            "--min-hit-rate",
            "0.20",
            "--p95-ms-max",
            "45000",
            "--expect-vec-ready",
            "0",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 2:
        pytest.skip(proc.stdout[-1200:] + proc.stderr[-1200:])
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
