from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional


@dataclass(frozen=True)
class KVStoreConfig:
    """
    SQLite-backed KV store.

    Default path intentionally lives under `data/` so it stays untracked.
    """

    db_path: str = os.getenv("QUENTIN_KVSTORE_PATH", "data/kv_store.sqlite3")
    sqlite_timeout_s: float = 5.0


class KVStore:
    """
    A tiny persistent KV store API used across Research/Skills/Tracing.

    Notes:
    - Values are stored as JSON strings; non-JSON-serializable objects fall back to `str()`.
    - Operations are async but implemented via `asyncio.to_thread` to avoid blocking loops.
    """

    def __init__(self, config: Optional[KVStoreConfig] = None) -> None:
        self.config = config or KVStoreConfig()
        self._db_path = Path(self.config.db_path)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(self._init_db)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=self.config.sqlite_timeout_s,
            isolation_level=None,  # autocommit; we manage transactions manually where needed
        )
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kv_updated_at ON kv(updated_at);")

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))

    @staticmethod
    def _loads(raw: str) -> Any:
        try:
            return json.loads(raw)
        except Exception:
            return raw

    async def save(self, key: str, value: Any) -> None:
        await self._ensure_initialized()

        raw = self._dumps(value)
        now = time.time()

        def _op() -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO kv(key, value_json, updated_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                    (key, raw, now),
                )

        await asyncio.to_thread(_op)

    async def get(self, key: str) -> Any:
        await self._ensure_initialized()

        def _op() -> Any:
            with self._connect() as conn:
                cur = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,))
                row = cur.fetchone()
                if not row:
                    return None
                return self._loads(row[0])

        return await asyncio.to_thread(_op)

    async def append_list(self, key: str, item: Any) -> None:
        await self._ensure_initialized()

        item_raw = self._dumps(item)
        now = time.time()

        def _op() -> None:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    cur = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,))
                    row = cur.fetchone()
                    if not row:
                        lst: list[Any] = []
                    else:
                        val = self._loads(row[0])
                        if val is None:
                            lst = []
                        elif isinstance(val, list):
                            lst = val
                        else:
                            lst = [val]

                    lst.append(self._loads(item_raw))
                    conn.execute(
                        "INSERT INTO kv(key, value_json, updated_at) VALUES(?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                        (key, self._dumps(lst), now),
                    )
                    conn.execute("COMMIT;")
                except Exception:
                    conn.execute("ROLLBACK;")
                    raise

        await asyncio.to_thread(_op)

    async def hset(self, key: str, field: str, value: Any) -> None:
        """
        Hash-like set: store a dict under `key` and set `dict[field] = value`.
        Implemented on top of the same SQLite KV table.
        """
        await self._ensure_initialized()

        now = time.time()
        field_s = str(field)

        def _op() -> None:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    cur = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,))
                    row = cur.fetchone()
                    if not row:
                        d: dict[str, Any] = {}
                    else:
                        val = self._loads(row[0])
                        d = val if isinstance(val, dict) else {}
                    d[field_s] = value
                    conn.execute(
                        "INSERT INTO kv(key, value_json, updated_at) VALUES(?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                        (key, self._dumps(d), now),
                    )
                    conn.execute("COMMIT;")
                except Exception:
                    conn.execute("ROLLBACK;")
                    raise

        await asyncio.to_thread(_op)

    async def hget(self, key: str, field: str) -> Any:
        """
        Hash-like get: read dict stored under `key` and return `dict.get(field)`.
        """
        await self._ensure_initialized()
        field_s = str(field)

        def _op() -> Any:
            with self._connect() as conn:
                cur = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,))
                row = cur.fetchone()
                if not row:
                    return None
                val = self._loads(row[0])
                if not isinstance(val, dict):
                    return None
                return val.get(field_s)

        return await asyncio.to_thread(_op)

    async def list_keys(self, prefix: str = "") -> List[str]:
        """
        Return all keys starting with `prefix`.
        Research/experiment analytics uses this.
        """
        await self._ensure_initialized()

        def _op() -> List[str]:
            with self._connect() as conn:
                if not prefix:
                    cur = conn.execute("SELECT key FROM kv")
                else:
                    cur = conn.execute("SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",))
                return [r[0] for r in cur.fetchall()]

        return await asyncio.to_thread(_op)
