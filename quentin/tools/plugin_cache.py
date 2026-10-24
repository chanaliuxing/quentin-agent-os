from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class CacheHit:
    value: Any
    created_at: float
    expires_at: float
    stale: bool = False


class ToolSqliteCache:
    def __init__(self, *, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_cache (
                  k TEXT PRIMARY KEY,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  v TEXT NOT NULL
                )
                """
            )

    def get(self, key: str, *, allow_stale_sec: int = 0) -> Optional[CacheHit]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT v, created_at, expires_at FROM tool_cache WHERE k=?",
                (str(key),),
            ).fetchone()
            if not row:
                return None
            v_s, created_at, expires_at = row
            try:
                expires_at_f = float(expires_at)
            except Exception:
                expires_at_f = 0.0
            stale = False
            if expires_at_f and expires_at_f < now:
                stale_deadline = expires_at_f + max(0, int(allow_stale_sec or 0))
                if now <= stale_deadline:
                    stale = True
                else:
                    try:
                        conn.execute("DELETE FROM tool_cache WHERE k=?", (str(key),))
                    except Exception:
                        pass
                    return None
            try:
                v = json.loads(v_s)
            except Exception:
                v = v_s
            return CacheHit(value=v, created_at=float(created_at or 0.0), expires_at=expires_at_f, stale=stale)

    def set(self, *, key: str, value: Any, ttl_sec: int, max_bytes: int = 0, namespace: str = "") -> None:
        now = time.time()
        expires_at = now + max(0, int(ttl_sec or 0))
        try:
            v_s = json.dumps(value, ensure_ascii=False)
        except Exception:
            v_s = json.dumps({"repr": repr(value)}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tool_cache(k, created_at, expires_at, v) VALUES(?, ?, ?, ?)",
                (str(key), float(now), float(expires_at), str(v_s)),
            )
            if max_bytes > 0:
                self._evict_to_budget(conn=conn, namespace=str(namespace or ""), max_bytes=int(max_bytes))

    def _evict_to_budget(self, *, conn: sqlite3.Connection, namespace: str, max_bytes: int) -> None:
        if max_bytes <= 0:
            return
        prefix = f"{namespace}:" if namespace else ""
        rows = conn.execute(
            "SELECT k, v, created_at FROM tool_cache WHERE (? = '' OR k LIKE ?)",
            (prefix, f"{prefix}%"),
        ).fetchall()
        if not rows:
            return
        total_bytes = 0
        items: list[tuple[str, int, float]] = []
        for key, value_s, created_at in rows:
            try:
                entry_bytes = len(str(value_s).encode("utf-8"))
            except Exception:
                entry_bytes = 0
            total_bytes += entry_bytes
            items.append((str(key), entry_bytes, float(created_at or 0.0)))
        if total_bytes <= max_bytes:
            return
        items.sort(key=lambda item: item[2])  # oldest first
        for key, entry_bytes, _created_at in items:
            if total_bytes <= max_bytes:
                break
            try:
                conn.execute("DELETE FROM tool_cache WHERE k=?", (key,))
            except Exception:
                continue
            total_bytes -= entry_bytes
