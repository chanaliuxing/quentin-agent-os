from __future__ import annotations

import click

from scripts.apply_pg_migrations import apply_migrations


@click.group("pg")
def pg_group() -> None:
    """Postgres utility commands."""
    pass


@pg_group.command("migrate")
def pg_migrate() -> None:
    """Apply PG migrations (requires PG_* env or PG_DSN)."""
    apply_migrations()
