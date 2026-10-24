from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from quentin.memory.champion.qdrant_rest import QdrantRestClient


def _pg_dsn() -> str | None:
    env_dsn = (os.getenv("PG_DSN") or "").strip()
    if env_dsn:
        return env_dsn
    host = (os.getenv("PG_HOST") or "").strip()
    if not host:
        return None
    port = (os.getenv("PG_PORT") or "5432").strip()
    user = (os.getenv("PG_USER") or "postgres").strip()
    password = os.getenv("PG_PASSWORD", "")
    db = (os.getenv("PG_DB") or "postgres").strip()
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _check_qdrant() -> tuple[bool, str]:
    base_url = (os.getenv("QDRANT_URL") or "http://localhost:6333").strip()
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
    try:
        timeout_s = float(os.getenv("QUENTIN_QDRANT_TIMEOUT_S", "3") or 3)
    except Exception:
        timeout_s = 3.0
    try:
        client = QdrantRestClient(base_url=base_url, timeout_s=timeout_s, api_key=api_key)
        ready = client.ready()
        return bool(ready), f"readyz:{base_url}" if ready else f"not_ready:{base_url}"
    except Exception as e:
        return False, f"qdrant_error:{e}"


def _check_postgres() -> tuple[bool, str]:
    dsn = _pg_dsn()
    if not dsn:
        return False, "missing_pg_dsn_or_pg_host"
    try:
        import psycopg

        conn = psycopg.connect(dsn, connect_timeout=3)
        try:
            cur = conn.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return bool(row), "select_1_ok"
        finally:
            conn.close()
    except Exception as e:
        return False, f"postgres_error:{e}"


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=repo_root / ".env", override=False)

    parser = argparse.ArgumentParser(description="Check Champion (Qdrant + Postgres) environment readiness.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when Champion dependencies are not ready.",
    )
    args = parser.parse_args()

    q_ok, q_msg = _check_qdrant()
    pg_ok, pg_msg = _check_postgres()
    checks = [
        {"source": "qdrant", "ok": q_ok, "detail": q_msg},
        {"source": "postgres", "ok": pg_ok, "detail": pg_msg},
    ]
    if q_ok and pg_ok:
        print({"status": "ok", "checks": checks})
        return

    print({"status": "not_ready", "checks": checks})
    if bool(args.strict):
        raise SystemExit(5)


if __name__ == "__main__":
    main()
