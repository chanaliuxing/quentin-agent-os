from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Iterable
from quentin.utils.time import now_utc

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError as exc:  # pragma: no cover - import guard
    raise RuntimeError(
        "psycopg is required for Postgres memory store. "
        "Install with `pip install psycopg[binary]`."
    ) from exc

from .store_base import MemoryStore
from .models import MemoryRecord, MemoryQuery, MemoryTier


def _env_pg_dsn() -> Optional[str]:
    host = os.getenv("PG_HOST")
    if not host:
        return None
    port = os.getenv("PG_PORT", "5432")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


class PostgresMemoryStore(MemoryStore):
    """
    Postgres-backed MemoryStore.
    - Stores vectors/relations as JSONB.
    - Optional pgvector can be added later; current vector search is client-side cosine.
    """

    def __init__(self, dsn: Optional[str] = None, use_pgvector: bool = True):
        self.dsn = dsn or _env_pg_dsn()
        if not self.dsn:
            raise ValueError("PostgresMemoryStore requires DSN or PG_* env vars.")
        # Mask password for logging
        safe_dsn = self.dsn.split("@")[-1] if "@" in self.dsn else "..."
        print(f"DEBUG: PostgresMemoryStore DSN host/db: {safe_dsn}")
        self._conn: Optional[psycopg.Connection] = None
        self.use_pgvector = use_pgvector
        self._fts_enabled = True
        self.namespace = (os.getenv("QUENTIN_MEMORY_NAMESPACE") or "default").strip() or "default"

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None:
            self._conn = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=False)
            # Optional fast-ingest settings for benchmarks / bulk loads.
            # This trades durability for speed; do not enable for production.
            if (os.getenv("QUENTIN_PG_FAST_INGEST") or "").strip().lower() in ("1", "true", "yes", "on"):
                try:
                    self._conn.execute("SET synchronous_commit TO OFF;")
                    self._conn.commit()
                except Exception:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
        return self._conn

    def _read_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        self.conn.commit()
        return row

    def _read_all(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        self.conn.commit()
        return list(rows)

    def _configure_init_timeouts(self) -> None:
        lock_timeout_ms = int(os.getenv("QUENTIN_PG_INIT_LOCK_TIMEOUT_MS", "3000") or 3000)
        statement_timeout_ms = int(os.getenv("QUENTIN_PG_INIT_STATEMENT_TIMEOUT_MS", "15000") or 15000)
        self.conn.execute(f"SET lock_timeout TO '{lock_timeout_ms}ms';")
        self.conn.execute(f"SET statement_timeout TO '{statement_timeout_ms}ms';")
        self.conn.commit()

    def init(self) -> None:
        print("DEBUG: PostgresMemoryStore.init() called")
        self._configure_init_timeouts()
        
        # 1. Try to install pgvector extension
        if self.use_pgvector:
            try:
                self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                self.conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
                self.conn.commit()
            except Exception as e:
                print(f"DEBUG: pgvector init failed (extensions skipped): {e}")
                self.conn.rollback()
                self.use_pgvector = False

        # 2. Define schema (keep parity with SqliteMemoryStore where possible)
        vector_col_def = "vector_emb vector," if self.use_pgvector else ""
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL DEFAULT 'default',
                tier TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'episodic',
                topic TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL,
                domain TEXT,
                importance DOUBLE PRECISION NOT NULL,
                last_accessed_at TIMESTAMPTZ,
                access_count INTEGER NOT NULL DEFAULT 0,
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                consolidated_from_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                supersedes_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                vector JSONB,
                {vector_col_def}
                relations JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                update_policy JSONB,
                update_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                decayed BOOLEAN NOT NULL DEFAULT FALSE,
                file_mtime DOUBLE PRECISION,
                file_size BIGINT,
                content_hash TEXT
            );
            """
        )
        self.conn.commit()

        # 2b. Forward-compat: add missing columns if table pre-existed with an older schema.
        # Keep this best-effort; if a column already exists or a type differs, we just skip.
        alter_cols = [
            ("namespace", "TEXT NOT NULL DEFAULT 'default'"),
            ("topic", "TEXT"),
            ("domain", "TEXT"),
            ("supersedes_ids", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
            ("update_policy", "JSONB"),
            ("update_history", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
            ("file_mtime", "DOUBLE PRECISION"),
            ("file_size", "BIGINT"),
            ("content_hash", "TEXT"),
        ]
        for col, coldef in alter_cols:
            try:
                self.conn.execute(f"ALTER TABLE memories ADD COLUMN IF NOT EXISTS {col} {coldef};")
                self.conn.commit()
            except Exception:
                self.conn.rollback()

        # 3. Create indexes
        try:
            # Safe to attempt these even if extension missing (pg_trgm might be missing too though)
            # Check if pg_trgm exists? safer to just try/except blocks for indexes
            try:
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS memories_namespace_created_idx ON memories (namespace, created_at DESC);"
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
            # Sparse (FTS): generated tsvector column + GIN index.
            try:
                self.conn.execute(
                    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content,''))) STORED;"
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
            try:
                self.conn.execute("CREATE INDEX IF NOT EXISTS memories_content_tsv_gin ON memories USING gin (content_tsv);")
                self.conn.commit()
            except Exception:
                self.conn.rollback()

            if self.use_pgvector:  # Assuming pg_trgm enabled with vector above
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS memories_content_trgm ON memories USING gin (content gin_trgm_ops);"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS memories_vector_emb_idx ON memories USING ivfflat (vector_emb) WITH (lists = 100);"
                )
            self.conn.commit()
        except Exception as e:
            print(f"DEBUG: Index creation warning: {e}")
            self.conn.rollback()

        # Verify table creation
        row = self._read_one("SELECT to_regclass('public.memories');")
        print(f"DEBUG: Table 'memories' check: {row}")

    def _row_to_record(self, row: Dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            tier=MemoryTier(row["tier"]),
            kind=row.get("kind", "episodic"),
            topic=row.get("topic"),
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=row["source"],
            domain=row.get("domain"),
            importance=row["importance"],
            last_accessed_at=row.get("last_accessed_at"),
            access_count=row["access_count"],
            tags=row["tags"] or [],
            metadata=row["metadata"] or {},
            consolidated_from_ids=row["consolidated_from_ids"] or [],
            supersedes_ids=row.get("supersedes_ids") or [],
            vector=row.get("vector") or row.get("vector_emb"),
            relations=row.get("relations") or {},
        )

    def add(self, record: MemoryRecord) -> None:
        params = self._record_params(record)
        
        cols = """
            id, namespace, tier, kind, topic, content, created_at, updated_at, source, domain,
            importance, last_accessed_at, access_count, tags,
            metadata, consolidated_from_ids, supersedes_ids, vector, relations, update_policy, update_history, decayed,
            file_mtime, file_size, content_hash
        """
        vals = """
            %(id)s, %(namespace)s, %(tier)s, %(kind)s, %(topic)s, %(content)s, %(created_at)s, %(updated_at)s, %(source)s, %(domain)s,
            %(importance)s, %(last_accessed_at)s, %(access_count)s, %(tags)s,
            %(metadata)s, %(consolidated_from_ids)s, %(supersedes_ids)s, %(vector)s, %(relations)s, %(update_policy)s, %(update_history)s, FALSE,
            %(file_mtime)s, %(file_size)s, %(content_hash)s
        """

        if self.use_pgvector:
            cols += ", vector_emb"
            vals += ", %(vector_emb)s"
            params["vector_emb"] = self._to_pgvector_literal(record.vector) if record.vector else None
            
        self.conn.execute(
            f"INSERT INTO memories ({cols}) VALUES ({vals})",
            params,
        )
        self.conn.commit()

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        row = self._read_one(
            "SELECT * FROM memories WHERE id = %(id)s AND namespace = %(namespace)s AND decayed = FALSE",
            {"id": record_id, "namespace": self.namespace},
        )
        return self._row_to_record(row) if row else None

    def update(self, record: MemoryRecord) -> None:
        params = self._record_params(record)
        
        set_clause = """
            tier = %(tier)s,
            kind = %(kind)s,
            topic = %(topic)s,
            content = %(content)s,
            updated_at = %(updated_at)s,
            source = %(source)s,
            domain = %(domain)s,
            importance = %(importance)s,
            last_accessed_at = %(last_accessed_at)s,
            access_count = %(access_count)s,
            tags = %(tags)s,
            metadata = %(metadata)s,
            consolidated_from_ids = %(consolidated_from_ids)s,
            supersedes_ids = %(supersedes_ids)s,
            vector = %(vector)s,
            relations = %(relations)s,
            update_policy = %(update_policy)s,
            update_history = %(update_history)s,
            file_mtime = %(file_mtime)s,
            file_size = %(file_size)s,
            content_hash = %(content_hash)s
        """
        
        if self.use_pgvector:
            set_clause += ", vector_emb = %(vector_emb)s"
            params["vector_emb"] = self._to_pgvector_literal(record.vector) if record.vector else None

        self.conn.execute(
            f"UPDATE memories SET {set_clause} WHERE id = %(id)s AND namespace = %(namespace)s",
            params,
        )
        self.conn.commit()

    def touch_access_many(self, record_ids: List[str], at: datetime) -> None:
        ids = [str(x or "").strip() for x in (record_ids or [])]
        ids = [x for x in ids if x]
        if not ids:
            return
        self.conn.execute(
            """
            UPDATE memories
            SET last_accessed_at = %(at)s, access_count = access_count + 1
            WHERE id = ANY(%(ids)s) AND namespace = %(namespace)s AND decayed = FALSE
            """,
            {"at": at, "ids": ids, "namespace": self.namespace},
        )
        self.conn.commit()

    def search(self, query: MemoryQuery) -> List[MemoryRecord]:
        if query.vector:
            return self._vector_search(query)

        if query.text and (query.text_mode or "").lower() == "fts":
            scored = self.search_text_with_scores(query)
            return [rec for rec, _ in scored]

        sql = "SELECT * FROM memories WHERE decayed = FALSE AND namespace = %(namespace)s"
        params: Dict[str, Any] = {"namespace": self.namespace}

        if query.tier:
            sql += " AND tier = %(tier)s"
            params["tier"] = query.tier.value

        if query.min_importance > 0:
            sql += " AND importance >= %(importance)s"
            params["importance"] = query.min_importance

        if query.since:
            sql += " AND created_at >= %(since)s"
            params["since"] = query.since

        if query.text:
            sql += " AND content ILIKE %(text)s"
            params["text"] = f"%{query.text}%"

        if query.tags_any:
            tag_clauses = []
            for idx, tag in enumerate(query.tags_any):
                key = f"tag_{idx}"
                tag_clauses.append(f"tags::text ILIKE %({key})s")
                params[key] = f"%\"{tag}\"%"
            sql += " AND " + " AND ".join(tag_clauses)

        if query.kind:
            sql += " AND kind = %(kind)s"
            params["kind"] = query.kind

        sql += " ORDER BY importance DESC, created_at DESC LIMIT %(limit)s"
        params["limit"] = query.top_k

        rows = self._read_all(sql, params)
        return [self._row_to_record(r) for r in rows]

    def search_text_with_scores(self, query: MemoryQuery) -> List[tuple[MemoryRecord, float]]:
        if not query.text:
            return []
        
        # ts_rank based FTS (prefer generated tsvector column for index use).
        # For code-like queries, stemming is harmful; prefer 'simple' config.
        cfg = "simple" if (str(getattr(query, "domain", "") or "").strip().lower() == "code") else "english"
        sql = """
            SELECT *, ts_rank(content_tsv, websearch_to_tsquery(%(cfg)s, %(text)s)) AS score
            FROM memories
            WHERE decayed = FALSE
              AND namespace = %(namespace)s
              AND content_tsv @@ websearch_to_tsquery(%(cfg)s, %(text)s)
        """
        params: Dict[str, Any] = {"text": query.text, "cfg": cfg, "namespace": self.namespace}
        
        if query.tier:
            sql += " AND tier = %(tier)s"
            params["tier"] = query.tier.value
        if query.kind:
            sql += " AND kind = %(kind)s"
            params["kind"] = query.kind
        if query.min_importance > 0:
            sql += " AND importance >= %(importance)s"
            params["importance"] = query.min_importance
            
        sql += " ORDER BY score DESC LIMIT %(limit)s"
        params["limit"] = query.top_k
        
        rows = self._read_all(sql, params)
        
        results: List[tuple[MemoryRecord, float]] = []
        for row in rows:
            rec = self._row_to_record(row)
            # Normalize: ts_rank is 0..1 already, but 1 / (1 + rank) is OpenClaw style
            # For Postgres we can just use the rank, or normalize it similarly.
            rank = float(row["score"])
            norm = rank / (rank + 1.0) if rank > 0 else 0.0
            results.append((rec, norm))
        return results

    def _vector_search(self, query: MemoryQuery) -> List[MemoryRecord]:
        if self.use_pgvector:
            return self._vector_search_pgvector(query)
        return self._vector_search_client(query)

    def _vector_search_pgvector(self, query: MemoryQuery) -> List[MemoryRecord]:
        qv = query.vector or []
        if not qv:
            return []
        dim = len(qv)
        base_sql = "SELECT *, (vector_emb <=> %(query_vec)s) AS dist FROM memories WHERE decayed = FALSE AND namespace = %(namespace)s"
        params: Dict[str, Any] = {"query_vec": self._to_pgvector_literal(qv, dim), "namespace": self.namespace}
        if query.tier:
            base_sql += " AND tier = %(tier)s"
            params["tier"] = query.tier.value
        if query.kind:
            base_sql += " AND kind = %(kind)s"
            params["kind"] = query.kind
        if query.min_importance > 0:
            base_sql += " AND importance >= %(importance)s"
            params["importance"] = query.min_importance
        base_sql += " AND vector_emb IS NOT NULL"
        base_sql += " ORDER BY dist ASC LIMIT %(limit)s"
        params["limit"] = query.top_k
        rows = self._read_all(base_sql, params)
        return [self._row_to_record(r) for r in rows]

    def _vector_search_client(self, query: MemoryQuery) -> List[MemoryRecord]:
        base_sql = "SELECT * FROM memories WHERE decayed = FALSE AND namespace = %(namespace)s"
        params: Dict[str, Any] = {"namespace": self.namespace}
        if query.tier:
            base_sql += " AND tier = %(tier)s"
            params["tier"] = query.tier.value
        if query.kind:
            base_sql += " AND kind = %(kind)s"
            params["kind"] = query.kind
        if query.min_importance > 0:
            base_sql += " AND importance >= %(importance)s"
            params["importance"] = query.min_importance

        base_sql += " ORDER BY importance DESC, created_at DESC LIMIT %(limit)s"
        params["limit"] = max(query.top_k * 10, 50)

        rows = self._read_all(base_sql, params)

        qv = query.vector or []
        qnorm = math.sqrt(sum(x * x for x in qv)) or 1.0
        scored: List[tuple[float, MemoryRecord]] = []
        for row in rows:
            rec = self._row_to_record(row)
            vec = rec.vector or []
            if not vec or len(vec) != len(qv):
                continue
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            dot = sum(a * b for a, b in zip(qv, vec))
            score = dot / (norm * qnorm)
            scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[: query.top_k]]

    def promote(self, record_id: str, to_tier: MemoryTier) -> None:
        self.conn.execute(
            "UPDATE memories SET tier = %(tier)s, updated_at = %(updated_at)s WHERE id = %(id)s AND namespace = %(namespace)s",
            {"tier": to_tier.value, "id": record_id, "updated_at": now_utc(), "namespace": self.namespace},
        )
        self.conn.commit()

    def reindex_indexes(self) -> Dict[str, Any]:
        try:
            try:
                self.conn.execute("REINDEX TABLE CONCURRENTLY memories;")
                self.conn.commit()
                return {"status": "ok", "strategy": "concurrently"}
            except Exception:
                self.conn.rollback()
                self.conn.execute("REINDEX TABLE memories;")
                self.conn.commit()
                return {"status": "ok", "strategy": "blocking"}
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            return {"status": "failed", "error": str(e)}

    def mark_decayed(self, record_id: str) -> None:
        self.conn.execute(
            "UPDATE memories SET decayed = TRUE WHERE id = %(id)s AND namespace = %(namespace)s",
            {"id": record_id, "namespace": self.namespace},
        )
        self.conn.commit()

    def get_candidates_for_consolidation(
        self,
        tier: MemoryTier | str,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
        rows = self._read_all(
            """
            SELECT * FROM memories
            WHERE tier = %(tier)s AND namespace = %(namespace)s AND decayed = FALSE
            ORDER BY created_at DESC
            LIMIT %(limit)s
            """,
            {"tier": tier_val, "limit": limit, "namespace": self.namespace},
        )
        return [self._row_to_record(r) for r in rows]

    def _record_params(self, record: MemoryRecord) -> Dict[str, Any]:
        # psycopg needs explicit JSON wrappers for jsonb columns to avoid "json string inside jsonb" pitfalls.
        return {
            "id": record.id,
            "namespace": self.namespace,
            "tier": record.tier.value,
            "kind": record.kind,
            "topic": record.topic,
            "content": record.content,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "source": record.source,
            "domain": record.domain,
            "importance": record.importance,
            "last_accessed_at": record.last_accessed_at,
            "access_count": record.access_count,
            "tags": Jsonb(record.tags or []),
            "metadata": Jsonb(record.metadata or {}),
            "consolidated_from_ids": Jsonb(record.consolidated_from_ids or []),
            "supersedes_ids": Jsonb(record.supersedes_ids or []),
            "vector": json.dumps(record.vector) if record.vector is not None else None,
            "relations": Jsonb(record.relations or {}),
            "update_policy": Jsonb(record.update_policy.to_dict()) if record.update_policy else None,
            "update_history": Jsonb(record.update_history or []),
            "file_mtime": (record.metadata or {}).get("file_mtime"),
            "file_size": (record.metadata or {}).get("file_size"),
            "content_hash": (record.metadata or {}).get("content_hash"),
        }

    def _to_pgvector_literal(self, vec: Iterable[float], dim: Optional[int] = None) -> str:
        as_list = list(vec)
        if dim is not None and len(as_list) != dim:
            raise ValueError("Vector dimensionality mismatch for pgvector")
        # pgvector binary parameter binding differs by driver; here use literal cast
        return f"[{','.join(str(x) for x in as_list)}]"
