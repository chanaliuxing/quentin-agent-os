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


def test_check_champion_runtime_fails_when_memory_store_not_champion(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["QUENTIN_MEMORY_STORE"] = "sqlite"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_champion_runtime.py"),
            "--strict",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "memory_store_not_champion" in (proc.stdout or "")


def test_check_champion_runtime_passes_when_champion_and_qdrant_ready() -> None:
    dsn = _pg_dsn_from_env_or_default()
    qdrant_url = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").strip()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion runtime check.")
    if not _qdrant_ready(qdrant_url):
        pytest.skip("Qdrant not ready for champion runtime check.")

    repo_root = Path(__file__).resolve().parents[2]
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
            str(repo_root / "scripts" / "check_champion_runtime.py"),
            "--strict",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert "\"status\": \"ok\"" in (proc.stdout or "")
