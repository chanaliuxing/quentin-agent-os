# meta_agent/memory/store_sqlite.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from typing import List, Optional, Dict, Any
from pathlib import Path
import sqlite3
import json
import datetime as dt

from meta_agent.memory.types import MemoryRecord, MemoryTier


class SqliteMemoryStore:
    """
    一个尽量简单的 SQLite memory store：
    - 一张 memory_records 表
    - 支持 CRUD + 简单 LIKE 搜索
    """

    def __init__(self, db_path: str | Path = "data/memory/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL,
    importance REAL NOT NULL,
    recency_score REAL NOT NULL,
    usage_count INTEGER NOT NULL,
    last_accessed_at TEXT
);
"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory_records(tier);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_records(kind);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_records(created_at);")
        self._conn.commit()

    def upsert(self, rec: MemoryRecord) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
INSERT INTO memory_records (
    id, tier, created_at, updated_at, kind, text, metadata,
    importance, recency_score, usage_count, last_accessed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    tier=excluded.tier,
    updated_at=excluded.updated_at,
    kind=excluded.kind,
    text=excluded.text,
    metadata=excluded.metadata,
    importance=excluded.importance,
    recency_score=excluded.recency_score,
    usage_count=excluded.usage_count,
    last_accessed_at=excluded.last_accessed_at;
""",
            (
                rec.id,
                rec.tier.value,
                rec.created_at,
                rec.updated_at,
                rec.kind,
                rec.text,
                json.dumps(rec.metadata, ensure_ascii=False),
                rec.importance,
                rec.recency_score,
                rec.usage_count,
                rec.last_accessed_at,
            ),
        )
        self._conn.commit()

    def get(self, rec_id: str) -> Optional[MemoryRecord]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM memory_records WHERE id = ?", (rec_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def delete(self, rec_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memory_records WHERE id = ?", (rec_id,))
        self._conn.commit()

    def list_by_tier(self, tier: MemoryTier, limit: int = 1000) -> List[MemoryRecord]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM memory_records WHERE tier = ? ORDER BY created_at DESC LIMIT ?",
            (tier.value, limit),
        )
        rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def search(
        self,
        query: str,
        tiers: Optional[List[MemoryTier]] = None,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        cur = self._conn.cursor()
        params: list[Any] = []
        where = []

        if tiers:
            tier_vals = [t.value for t in tiers]
            placeholders = ",".join("?" for _ in tier_vals)
            where.append(f"tier IN ({placeholders})")
            params.extend(tier_vals)

        if kind:
            where.append("kind = ?")
            params.append(kind)

        if query:
            where.append("text LIKE ?")
            params.append(f"%{query}%")

        where_sql = " AND ".join(where) if where else "1=1"
        sql = f"""
SELECT * FROM memory_records
WHERE {where_sql}
ORDER BY importance DESC, recency_score DESC
LIMIT ?
"""
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def touch(self, rec_id: str) -> None:
        now = now_iso()
        cur = self._conn.cursor()
        cur.execute(
            """
UPDATE memory_records
SET
  usage_count = usage_count + 1,
  last_accessed_at = ?,
  recency_score = MIN(recency_score + 0.1, 1.0)
WHERE id = ?;
""",
            (now, rec_id),
        )
        self._conn.commit()

    def bulk_update_tier(
        self,
        rec_ids: List[str],
        new_tier: MemoryTier,
    ) -> None:
        if not rec_ids:
            return
        now = now_iso()
        cur = self._conn.cursor()
        placeholders = ",".join("?" for _ in rec_ids)
        params = [new_tier.value, now] + rec_ids
        cur.execute(
            f"""
UPDATE memory_records
SET tier = ?, updated_at = ?
WHERE id IN ({placeholders});
""",
            params,
        )
        self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        return MemoryRecord(
            id=row["id"],
            tier=MemoryTier(row["tier"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            kind=row["kind"],
            text=row["text"],
            metadata=metadata,
            importance=row["importance"],
            recency_score=row["recency_score"],
            usage_count=row["usage_count"],
            last_accessed_at=row["last_accessed_at"],
        )
