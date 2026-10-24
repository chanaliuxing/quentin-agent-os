from __future__ import annotations
import sqlite3
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
import math
from quentin.utils.time import now_utc
from pathlib import Path

from .store_base import MemoryStore
from .models import MemoryRecord, MemoryQuery, MemoryTier, MemoryUpdatePolicy

try:
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    _np = None


class SqliteMemoryStore(MemoryStore):
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_enabled = os.getenv("QUENTIN_MEMORY_FTS", "").strip().lower() in ("1", "true", "yes", "on")
        self._vector_math_backend = "numpy" if _np is not None else "python"
        self._vector_fetch_strategy = (
            "two_phase"
            if os.getenv("QUENTIN_MEMORY_VECTOR_TWO_PHASE_FETCH", "1").strip().lower() in ("1", "true", "yes", "on")
            else "single_phase"
        )
        try:
            self._vector_scan_limit = int(os.getenv("QUENTIN_MEMORY_VECTOR_SCAN_LIMIT", "20000"))
        except Exception:
            self._vector_scan_limit = 20000

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self) -> None:
        # P5: Surgery Fifty-three - Knowledge Graph Schema (OpenClaw Parity)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                name TEXT PRIMARY KEY,
                kind TEXT NOT NULL DEFAULT 'generic',
                description TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_entity_map (
                memory_id TEXT,
                entity_name TEXT,
                weight REAL DEFAULT 1.0,
                PRIMARY KEY (memory_id, entity_name),
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE,
                FOREIGN KEY (entity_name) REFERENCES entities(name) ON DELETE CASCADE
            )
            """
        )
        
        # Create meta table for model consistency (OpenClaw Parity)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        
        # P5: Surgery One Hundred and Six - Embedding Cache (OpenClaw Parity)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                vector TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'episodic',
                topic TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                domain TEXT,
                importance REAL NOT NULL,
                last_accessed_at TEXT,
                access_count INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL,
                metadata TEXT NOT NULL,
                consolidated_from_ids TEXT NOT NULL,
                supersedes_ids TEXT NOT NULL DEFAULT '[]',
                vector TEXT,
                relations TEXT,
                update_policy TEXT,
                update_history TEXT NOT NULL DEFAULT '[]',
                decayed INTEGER NOT NULL DEFAULT 0,
                file_mtime REAL,
                file_size INTEGER,
                content_hash TEXT
            )
            """
        )
        self._ensure_columns()
        if self._fts_enabled:
            self._ensure_fts()
        self.conn.commit()

    def _ensure_columns(self) -> None:
        cur = self.conn.execute("PRAGMA table_info(memories)")
        cols = {row["name"] for row in cur.fetchall()}
        alters = []
        # ... existing alters ...
        if "file_mtime" not in cols:
            alters.append("ALTER TABLE memories ADD COLUMN file_mtime REAL")
        if "file_size" not in cols:
            alters.append("ALTER TABLE memories ADD COLUMN file_size INTEGER")
        if "content_hash" not in cols:
            alters.append("ALTER TABLE memories ADD COLUMN content_hash TEXT")
        if "last_read_offset" not in cols:
            alters.append("ALTER TABLE memories ADD COLUMN last_read_offset INTEGER DEFAULT 0")
        
        # Original alters
        if "topic" not in cols:
            alters.append("ALTER TABLE memories ADD COLUMN topic TEXT")
        # ... (other existing columns)

    def _ensure_fts(self) -> None:
        self.conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                memory_id UNINDEXED
            )
            """
        )
        self.conn.execute("DELETE FROM memories_fts")
        self.conn.execute(
            "INSERT INTO memories_fts(memory_id, content) SELECT id, content FROM memories WHERE decayed = 0"
        )

    def add(self, record: MemoryRecord) -> None:
        try:
            self._insert_record(record)
        except sqlite3.OperationalError as e:
            if "no such table: memories" not in str(e).lower():
                raise
            self.init()
            self._insert_record(record)
        if self._fts_enabled:
            self._fts_upsert(record)
        self.conn.commit()

    def _insert_record(self, record: MemoryRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO memories (
                id, tier, kind, topic, content, created_at, updated_at, source, domain,
                importance, last_accessed_at, access_count, tags,
                metadata, consolidated_from_ids, supersedes_ids, vector, relations,
                update_policy, update_history, decayed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                record.id,
                record.tier.value,
                record.kind,
                getattr(record, "topic", None),
                record.content,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                record.source,
                record.domain,
                record.importance,
                record.last_accessed_at.isoformat()
                if record.last_accessed_at
                else None,
                record.access_count,
                json.dumps(record.tags),
                json.dumps(record.metadata),
                json.dumps(record.consolidated_from_ids),
                json.dumps(record.supersedes_ids),
                json.dumps(record.vector) if record.vector is not None else None,
                json.dumps(record.relations),
                json.dumps(record.update_policy.to_dict() if record.update_policy else None),
                json.dumps(record.update_history),
            ),
        )

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        update_policy_raw = None
        try:
            update_policy_raw = json.loads(row["update_policy"]) if row["update_policy"] else None
        except Exception:
            update_policy_raw = None
        update_policy = None
        if isinstance(update_policy_raw, dict):
            update_policy = MemoryUpdatePolicy(
                promotion_rule=update_policy_raw.get("promotion_rule"),
                decay_rule=update_policy_raw.get("decay_rule"),
                consolidation_batch=update_policy_raw.get("consolidation_batch"),
            )
        
        # Safe extraction of topic (fallback to metadata if missing in older schema rows)
        topic = row["topic"] if "topic" in row.keys() else None
        meta = json.loads(row["metadata"])
        if topic is None and "topic" in meta:
            topic = meta["topic"]

        rec = MemoryRecord(
            id=row["id"],
            tier=MemoryTier(row["tier"]),
            kind=row["kind"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            source=row["source"],
            domain=row["domain"] if "domain" in row.keys() else None,
            importance=row["importance"],
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"])
            if row["last_accessed_at"]
            else None,
            access_count=row["access_count"],
            tags=json.loads(row["tags"]),
            metadata=meta,
            consolidated_from_ids=json.loads(row["consolidated_from_ids"]),
            supersedes_ids=json.loads(row["supersedes_ids"]) if row["supersedes_ids"] else [],
            vector=json.loads(row["vector"]) if row["vector"] else None,
            relations=json.loads(row["relations"]) if row["relations"] else {},
            update_policy=update_policy,
            update_history=json.loads(row["update_history"]) if row["update_history"] else [],
        )
        # Manually set topic as it might not be in MemoryRecord __init__ yet
        setattr(rec, "topic", topic)
        return rec

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        cur = self.conn.execute(
            "SELECT * FROM memories WHERE id = ? AND decayed = 0",
            (record_id,),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def update(self, record: MemoryRecord) -> None:
        self.conn.execute(
            """
            UPDATE memories SET
                tier = ?, kind = ?, topic = ?, content = ?, updated_at = ?, source = ?, domain = ?,
                importance = ?, last_accessed_at = ?, access_count = ?,
                tags = ?, metadata = ?, consolidated_from_ids = ?,
                supersedes_ids = ?, vector = ?, relations = ?,
                update_policy = ?, update_history = ?
            WHERE id = ?
            """,
            (
                record.tier.value,
                record.kind,
                getattr(record, "topic", None),
                record.content,
                record.updated_at.isoformat(),
                record.source,
                record.domain,
                record.importance,
                record.last_accessed_at.isoformat()
                if record.last_accessed_at
                else None,
                record.access_count,
                json.dumps(record.tags),
                json.dumps(record.metadata),
                json.dumps(record.consolidated_from_ids),
                json.dumps(record.supersedes_ids),
                json.dumps(record.vector) if record.vector is not None else None,
                json.dumps(record.relations),
                json.dumps(record.update_policy.to_dict() if record.update_policy else None),
                json.dumps(record.update_history),
                record.id,
            ),
        )
        if self._fts_enabled:
            self._fts_upsert(record)
        self.conn.commit()

    def touch_access_many(self, record_ids: List[str], at: datetime) -> None:
        ids = [str(x or "").strip() for x in (record_ids or [])]
        ids = [x for x in ids if x]
        if not ids:
            return
        ts = at.isoformat()
        self.conn.execute("BEGIN")
        try:
            self.conn.executemany(
                """
                UPDATE memories
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id = ? AND decayed = 0
                """,
                [(ts, rid) for rid in ids],
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def search(self, query: MemoryQuery) -> List[MemoryRecord]:
        if getattr(query, "vector", None) is not None:
            return self._vector_search(query)
        if query.text and (query.text_mode or "").lower() == "fts" and self._fts_enabled:
            scored = self.search_text_with_scores(query)
            return [rec for rec, _ in scored]
        sql = "SELECT * FROM memories WHERE decayed = 0"
        params: list = []
        token_filters: List[str] = []

        if query.tier:
            sql += " AND tier = ?"
            params.append(query.tier.value)

        if query.min_importance > 0:
            sql += " AND importance >= ?"
            params.append(query.min_importance)

        if query.since:
            sql += " AND created_at >= ?"
            params.append(query.since.isoformat())

        if query.text:
            text_mode = (query.text_mode or "").strip().lower()
            if text_mode in ("", "like"):
                # Lexical expansion (order-insensitive): require all meaningful query tokens.
                # This improves semantic-ish text recall where token order differs.
                tokens = self._tokenize_text_query(str(query.text))
                if tokens:
                    token_filters = list(tokens)
                    for tok in tokens:
                        sql += " AND content LIKE ?"
                        params.append(f"%{tok}%")
                else:
                    sql += " AND content LIKE ?"
                    params.append(f"%{query.text}%")
            else:
                sql += " AND content LIKE ?"
                params.append(f"%{query.text}%")

        if query.tags_any:
            # v1 简单实现：tag 字符串包含判断
            for tag in query.tags_any:
                sql += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')

        if query.kind:
            sql += " AND kind = ?"
            params.append(query.kind)

        # 重要度 + 时间排序
        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        lim = int(query.top_k)
        if token_filters:
            lim = max(lim * 20, 50)
        params.append(lim)

        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        records = [self._row_to_record(r) for r in rows]
        if token_filters:
            records = [r for r in records if self._content_matches_tokens(str(r.content or ""), token_filters)]
            records = records[: int(query.top_k)]
        return records

    def _tokenize_text_query(self, text: str) -> List[str]:
        parts = re.split(r"[^A-Za-z0-9_]+", str(text or "").lower())
        stop = {"the", "a", "an", "and", "or", "to", "in", "on", "of", "for", "is", "are", "be"}
        out: List[str] = []
        for p in parts:
            t = p.strip()
            if len(t) < 2 and not t.isdigit():
                continue
            if t in stop:
                continue
            out.append(t)
        # Keep order, unique.
        seen = set()
        uniq: List[str] = []
        for t in out:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        return uniq

    def _content_matches_tokens(self, content: str, tokens: List[str]) -> bool:
        text = str(content or "").lower()
        for tok in tokens:
            t = str(tok or "").strip().lower()
            if not t:
                continue
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])"
            if re.search(pattern, text) is None:
                return False
        return True

    def _fts_upsert(self, record: MemoryRecord) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO memories_fts(memory_id, content) VALUES (?, ?)",
            (record.id, record.content),
        )

    def search_text_with_scores(self, query: MemoryQuery) -> List[tuple[MemoryRecord, float]]:
        if not self._fts_enabled or not query.text:
            return []
        sql = """
            SELECT m.*, bm25(memories_fts) AS score
            FROM memories_fts
            JOIN memories m ON memories_fts.memory_id = m.id
            WHERE memories_fts MATCH ?
              AND m.decayed = 0
        """
        params: list[Any] = [query.text]
        if query.tier:
            sql += " AND m.tier = ?"
            params.append(query.tier.value)
        if query.kind:
            sql += " AND m.kind = ?"
            params.append(query.kind)
        if query.min_importance > 0:
            sql += " AND m.importance >= ?"
            params.append(query.min_importance)
        sql += " ORDER BY score ASC LIMIT ?"
        params.append(query.top_k)
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        
        results: List[tuple[MemoryRecord, float]] = []
        for row in rows:
            rec = self._row_to_record(row)
            # Normalize BM25 score using OpenClaw-inspired formula: 1 / (1 + max(0, score))
            # Note: SQLite BM25 is lower-is-better, and can be negative. 
            # We use absolute or offset to ensure positive for the 1/(1+x) formula.
            raw_score = float(row["score"])
            norm = 1.0 / (1.0 + abs(raw_score))
            results.append((rec, norm))
        return results

    def _vector_search(self, query: MemoryQuery) -> List[MemoryRecord]:
        if str(self._vector_fetch_strategy) == "single_phase":
            return self._vector_search_single_phase(query)

        base_sql = "SELECT id, vector FROM memories WHERE decayed = 0 AND vector IS NOT NULL"
        params: list[Any] = []
        if query.tier:
            base_sql += " AND tier = ?"
            params.append(query.tier.value)
        if query.kind:
            base_sql += " AND kind = ?"
            params.append(query.kind)
        if query.min_importance > 0:
            base_sql += " AND importance >= ?"
            params.append(query.min_importance)
        base_sql += " ORDER BY created_at DESC"
        if self._vector_scan_limit > 0:
            base_sql += " LIMIT ?"
            params.append(max(int(self._vector_scan_limit), max(query.top_k * 10, 50)))

        cur = self.conn.execute(base_sql, params)
        rows = cur.fetchall()

        qv = query.vector or []
        if not qv:
            return []

        candidate_ids: List[str] = []
        vectors: List[List[float]] = []
        for row in rows:
            rid = str(row["id"] or "")
            if not rid:
                continue
            raw_vector = row["vector"]
            if not raw_vector:
                continue
            try:
                vector = json.loads(raw_vector)
            except Exception:
                continue
            if not vector or len(vector) != len(qv):
                continue
            candidate_ids.append(rid)
            vectors.append(vector)

        if not candidate_ids:
            return []

        top_idx: List[int]
        if _np is not None:
            try:
                q = _np.asarray(qv, dtype=_np.float32)
                arr = _np.asarray(vectors, dtype=_np.float32)
                qnorm = float(_np.linalg.norm(q)) or 1.0
                norms = _np.linalg.norm(arr, axis=1)
                denom = norms * qnorm
                denom = _np.where(denom == 0.0, 1.0, denom)
                scores = (arr @ q) / denom
                order = _np.argsort(-scores)[: int(query.top_k)]
                top_idx = [int(i) for i in order.tolist()]
                return self._fetch_records_by_id_order([candidate_ids[i] for i in top_idx])
            except Exception:
                pass

        qnorm = math.sqrt(sum(x * x for x in qv)) or 1.0
        scored: List[tuple[float, int]] = []
        for idx, vector in enumerate(vectors):
            norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            dot = sum(a * b for a, b in zip(qv, vector))
            scored.append((dot / (norm * qnorm), idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_idx = [idx for _, idx in scored[: query.top_k]]
        return self._fetch_records_by_id_order([candidate_ids[i] for i in top_idx])

    def _vector_search_single_phase(self, query: MemoryQuery) -> List[MemoryRecord]:
        base_sql = "SELECT * FROM memories WHERE decayed = 0 AND vector IS NOT NULL"
        params: list[Any] = []
        if query.tier:
            base_sql += " AND tier = ?"
            params.append(query.tier.value)
        if query.kind:
            base_sql += " AND kind = ?"
            params.append(query.kind)
        if query.min_importance > 0:
            base_sql += " AND importance >= ?"
            params.append(query.min_importance)
        base_sql += " ORDER BY created_at DESC"
        if self._vector_scan_limit > 0:
            base_sql += " LIMIT ?"
            params.append(max(int(self._vector_scan_limit), max(query.top_k * 10, 50)))
        cur = self.conn.execute(base_sql, params)
        rows = cur.fetchall()

        qv = query.vector or []
        if not qv:
            return []

        records: List[MemoryRecord] = []
        vectors: List[List[float]] = []
        for row in rows:
            rec = self._row_to_record(row)
            if not rec.vector or len(rec.vector) != len(qv):
                continue
            records.append(rec)
            vectors.append(rec.vector)
        if not records:
            return []

        if _np is not None:
            try:
                q = _np.asarray(qv, dtype=_np.float32)
                arr = _np.asarray(vectors, dtype=_np.float32)
                qnorm = float(_np.linalg.norm(q)) or 1.0
                norms = _np.linalg.norm(arr, axis=1)
                denom = norms * qnorm
                denom = _np.where(denom == 0.0, 1.0, denom)
                scores = (arr @ q) / denom
                order = _np.argsort(-scores)[: int(query.top_k)]
                return [records[int(i)] for i in order.tolist()]
            except Exception:
                pass

        qnorm = math.sqrt(sum(x * x for x in qv)) or 1.0
        scored: List[tuple[float, MemoryRecord]] = []
        for rec in records:
            norm = math.sqrt(sum(x * x for x in (rec.vector or []))) or 1.0
            dot = sum(a * b for a, b in zip(qv, rec.vector or []))
            scored.append((dot / (norm * qnorm), rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[: query.top_k]]

    def _fetch_records_by_id_order(self, ids: List[str]) -> List[MemoryRecord]:
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        cur = self.conn.execute(
            f"SELECT * FROM memories WHERE decayed = 0 AND id IN ({placeholders})",
            ids,
        )
        rows = cur.fetchall()
        by_id: Dict[str, MemoryRecord] = {}
        for row in rows:
            rec = self._row_to_record(row)
            by_id[rec.id] = rec
        out: List[MemoryRecord] = []
        for rid in ids:
            rec = by_id.get(rid)
            if rec is not None:
                out.append(rec)
        return out

    def promote(self, record_id: str, to_tier: MemoryTier) -> None:
        self.conn.execute(
            "UPDATE memories SET tier = ?, updated_at = ? WHERE id = ?",
            (to_tier.value, now_utc().isoformat(), record_id),
        )
        self.conn.commit()

    def mark_decayed(self, record_id: str) -> None:
        self.conn.execute(
            "UPDATE memories SET decayed = 1 WHERE id = ?",
            (record_id,),
        )
        self.conn.commit()

    def get_candidates_for_consolidation(
        self,
        tier: MemoryTier | str,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        # v1：取最近一段时间 + importance 较高的 STS
        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
        cur = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE tier = ? AND decayed = 0
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tier_val, limit),
        )
        rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def reindex_indexes(self) -> Dict[str, Any]:
        db_path_str = str(self.db_path).strip()
        if db_path_str in {":memory:", "file::memory:"}:
            return {"status": "skipped", "reason": "in_memory_db"}

        db_path = Path(self.db_path)
        if not db_path.exists():
            return {"status": "skipped", "reason": "db_not_found"}

        tmp_base = db_path.with_name(f"{db_path.name}.tmp-{uuid.uuid4().hex}")
        backup_base = db_path.with_name(f"{db_path.name}.bak-{uuid.uuid4().hex}")

        had_conn = self._conn is not None
        if had_conn:
            try:
                self._conn.commit()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        try:
            self._copy_sqlite_bundle(db_path, tmp_base)
            tmp_conn = sqlite3.connect(tmp_base, check_same_thread=False)
            tmp_conn.row_factory = sqlite3.Row
            try:
                self._run_reindex_on_connection(tmp_conn)
                check = tmp_conn.execute("PRAGMA integrity_check").fetchone()
                if not check or str(check[0]).lower() != "ok":
                    raise RuntimeError(f"integrity_check failed: {check[0] if check else 'unknown'}")
            finally:
                tmp_conn.close()

            self._move_sqlite_bundle(db_path, backup_base)
            try:
                self._move_sqlite_bundle(tmp_base, db_path)
            except Exception:
                self._move_sqlite_bundle(backup_base, db_path)
                raise
            self._remove_sqlite_bundle(backup_base)
            return {"status": "ok", "strategy": "atomic_rebuild_swap"}
        except Exception as e:
            self._remove_sqlite_bundle(tmp_base)
            return {"status": "failed", "error": str(e)}

    def _run_reindex_on_connection(self, conn: sqlite3.Connection) -> None:
        conn.execute("REINDEX")
        if self._fts_enabled:
            conn.execute("DELETE FROM memories_fts")
            conn.execute(
                "INSERT INTO memories_fts(memory_id, content) SELECT id, content FROM memories WHERE decayed = 0"
            )
        conn.commit()

    def _sqlite_bundle_paths(self, base: Path) -> List[Path]:
        return [base, Path(f"{base}-wal"), Path(f"{base}-shm")]

    def _copy_sqlite_bundle(self, src_base: Path, dst_base: Path) -> None:
        copied = False
        for src, dst in zip(self._sqlite_bundle_paths(src_base), self._sqlite_bundle_paths(dst_base)):
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied = True
        if not copied:
            raise FileNotFoundError(f"sqlite bundle not found for {src_base}")

    def _move_sqlite_bundle(self, src_base: Path, dst_base: Path) -> None:
        moved = False
        for src, dst in zip(self._sqlite_bundle_paths(src_base), self._sqlite_bundle_paths(dst_base)):
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst.unlink()
            src.rename(dst)
            moved = True
        if not moved:
            raise FileNotFoundError(f"sqlite bundle not found for {src_base}")

    def _remove_sqlite_bundle(self, base: Path) -> None:
        for p in self._sqlite_bundle_paths(base):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
