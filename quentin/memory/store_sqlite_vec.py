from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from quentin.utils.time import now_utc

from .store_sqlite import SqliteMemoryStore
from .models import MemoryRecord, MemoryQuery, MemoryTier

logger = logging.getLogger(__name__)


class SqliteVecMemoryStore(SqliteMemoryStore):
    """
    Optional sqlite-vec backed store for vector search.
    Falls back to standard SqliteMemoryStore when extension is unavailable.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        vec_dim: Optional[int] = None,
        extension_path: Optional[str] = None,
    ) -> None:
        super().__init__(db_path)
        self.vec_dim = vec_dim or int(os.getenv("MEM_EMBED_DIM", "768"))
        self.extension_path = extension_path or os.getenv("QUENTIN_SQLITE_VEC_PATH")
        self._vec_ready = False

    def init(self) -> None:
        super().init()
        self._init_vec()

    def _init_vec(self) -> None:
        try:
            self.conn.enable_load_extension(True)
        except Exception as e:
            raise RuntimeError(f"sqlite extension loading unavailable: {e}") from e

        if self.extension_path:
            try:
                self.conn.load_extension(self.extension_path)
            except Exception as e:
                raise RuntimeError(f"failed to load sqlite-vec extension from QUENTIN_SQLITE_VEC_PATH={self.extension_path}: {e}") from e
        else:
            loaded = False
            # Prefer the python sqlite-vec package path when installed.
            try:
                import sqlite_vec  # type: ignore

                self.conn.load_extension(sqlite_vec.loadable_path())
                loaded = True
            except Exception:
                loaded = False

            for name in ("vec0", "sqlite_vec", "sqlite-vec"):
                if loaded:
                    break
                try:
                    self.conn.load_extension(name)
                    loaded = True
                    break
                except Exception:
                    continue
            if not loaded:
                raise RuntimeError("sqlite-vec extension not found; set QUENTIN_SQLITE_VEC_PATH")

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_vec_map (
                rowid INTEGER PRIMARY KEY,
                memory_id TEXT UNIQUE NOT NULL
            )
            """
        )
        self.conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
                embedding float[{self.vec_dim}]
            )
            """
        )
        self.conn.commit()
        self._vec_ready = True

    def _get_or_create_rowid(self, memory_id: str) -> int:
        cur = self.conn.execute(
            "SELECT rowid FROM memory_vec_map WHERE memory_id = ?",
            (memory_id,),
        )
        row = cur.fetchone()
        if row:
            return int(row["rowid"])
        cur = self.conn.execute(
            "INSERT INTO memory_vec_map(memory_id) VALUES (?)",
            (memory_id,),
        )
        return int(cur.lastrowid)

    def _upsert_vector(self, record: MemoryRecord) -> None:
        if not self._vec_ready or not record.vector:
            return
        rowid = self._get_or_create_rowid(record.id)
        self.conn.execute("DELETE FROM memory_vec WHERE rowid = ?", (rowid,))
        self.conn.execute(
            "INSERT INTO memory_vec(rowid, embedding) VALUES (?, ?)",
            (rowid, json.dumps(record.vector)),
        )

    def add(self, record: MemoryRecord) -> None:
        super().add(record)
        self._upsert_vector(record)
        self.conn.commit()

    def update(self, record: MemoryRecord) -> None:
        super().update(record)
        self._upsert_vector(record)
        self.conn.commit()

    def search(self, query: MemoryQuery) -> List[MemoryRecord]:
        if getattr(query, "vector", None) is None:
            return super().search(query)
        return self._vector_search_vec0(query)

    def search_text_with_scores(self, query: MemoryQuery) -> List[tuple[MemoryRecord, float]]:
        """Delegate to super (SqliteMemoryStore)."""
        return super().search_text_with_scores(query)

    def _vector_search_vec0(self, query: MemoryQuery) -> List[MemoryRecord]:
        if not self._vec_ready:
            return []
        qv = query.vector or []
        if not qv:
            return []

        sql = """
            SELECT m.*
            FROM memory_vec v
            JOIN memory_vec_map map ON map.rowid = v.rowid
            JOIN memories m ON m.id = map.memory_id
            WHERE v.embedding MATCH ?
              AND k = ?
              AND m.decayed = 0
        """
        params: List[Any] = [json.dumps(qv), int(query.top_k)]

        if query.tier:
            sql += " AND m.tier = ?"
            params.append(query.tier.value)
        if query.kind:
            sql += " AND m.kind = ?"
            params.append(query.kind)
        if query.min_importance > 0:
            sql += " AND m.importance >= ?"
            params.append(query.min_importance)

        sql += " ORDER BY v.distance ASC"
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def promote(self, record_id: str, to_tier: MemoryTier) -> None:
        self.conn.execute(
            "UPDATE memories SET tier = ?, updated_at = ? WHERE id = ?",
            (to_tier.value, now_utc().isoformat(), record_id),
        )
        self.conn.commit()

    def reindex_indexes(self) -> dict:
        if not self._vec_ready:
            return {"status": "skipped", "reason": "vec_not_ready"}
        try:
            self.conn.execute("BEGIN")
            self.conn.execute("DROP TABLE IF EXISTS memory_vec_map_new")
            self.conn.execute("DROP TABLE IF EXISTS memory_vec_new")
            self.conn.execute(
                """
                CREATE TABLE memory_vec_map_new (
                    rowid INTEGER PRIMARY KEY,
                    memory_id TEXT UNIQUE NOT NULL
                )
                """
            )
            self.conn.execute(
                f"""
                CREATE VIRTUAL TABLE memory_vec_new USING vec0(
                    embedding float[{self.vec_dim}]
                )
                """
            )
            cur = self.conn.execute(
                "SELECT id, vector FROM memories WHERE decayed = 0 AND vector IS NOT NULL"
            )
            for row in cur.fetchall():
                memory_id = row["id"]
                try:
                    vec = json.loads(row["vector"]) if row["vector"] else None
                except Exception:
                    vec = None
                if not vec:
                    continue
                ins = self.conn.execute(
                    "INSERT INTO memory_vec_map_new(memory_id) VALUES (?)",
                    (memory_id,),
                )
                rowid = int(ins.lastrowid)
                self.conn.execute(
                    "INSERT INTO memory_vec_new(rowid, embedding) VALUES (?, ?)",
                    (rowid, json.dumps(vec)),
                )

            self.conn.execute("ALTER TABLE memory_vec_map RENAME TO memory_vec_map_old")
            self.conn.execute("ALTER TABLE memory_vec_map_new RENAME TO memory_vec_map")
            self.conn.execute("ALTER TABLE memory_vec RENAME TO memory_vec_old")
            self.conn.execute("ALTER TABLE memory_vec_new RENAME TO memory_vec")
            self.conn.execute("DROP TABLE IF EXISTS memory_vec_map_old")
            self.conn.execute("DROP TABLE IF EXISTS memory_vec_old")
            self.conn.commit()
            return {"status": "ok", "strategy": "rebuild_swap"}
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            return {"status": "failed", "error": str(e)}
