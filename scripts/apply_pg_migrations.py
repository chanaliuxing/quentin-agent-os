from __future__ import annotations

import os
from pathlib import Path
import psycopg


def load_dsn() -> str:
    dsn = os.getenv("PG_DSN")
    if dsn:
        return dsn
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def apply_migrations(migrations_dir: str = "migrations") -> None:
    root = Path(__file__).resolve().parent.parent
    mig_dir = root / migrations_dir
    if not mig_dir.exists():
        raise FileNotFoundError(f"migrations dir not found: {mig_dir}")

    files = sorted(mig_dir.glob("*.sql"))
    if not files:
        print("No migration files found.")
        return

    dsn = load_dsn()
    print(f"Applying migrations to {dsn}")
    with psycopg.connect(dsn) as conn:
        for f in files:
            sql = f.read_text(encoding="utf-8")
            print(f"- Running {f.name}")
            with conn.cursor() as cur:
                cur.execute(sql)
        conn.commit()
    print("Migrations applied.")


if __name__ == "__main__":
    apply_migrations()
