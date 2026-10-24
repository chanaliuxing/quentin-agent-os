from __future__ import annotations

import logging
import os
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from quentin.utils.time import now_utc

from .models import MemoryQuery, MemoryRecord, MemoryTier
from .store_base import MemoryStore

try:
    from .store_postgres import PostgresMemoryStore
except Exception:  # pragma: no cover
    PostgresMemoryStore = None  # type: ignore

from .champion.qdrant_rest import QdrantRestClient, QdrantError
from .champion.reranker import build_reranker

logger = logging.getLogger(__name__)


class _NullCursor:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None):
        self._rows = list(rows or [])
        self.rowcount = 0

    def fetchone(self) -> Optional[Dict[str, Any]]:
        return self._rows[0] if self._rows else {"c": 0}

    def fetchall(self) -> List[Dict[str, Any]]:
        return list(self._rows)

    def close(self) -> None:
        return None


class _NullConn:
    def execute(self, _sql: str, _params: Optional[Dict[str, Any]] = None) -> _NullCursor:
        sql = str(_sql or "").lower()
        if "select value from meta" in sql:
            return _NullCursor([{"value": None}])
        if "count(*)" in sql:
            return _NullCursor([{"c": 0}])
        return _NullCursor()

    def cursor(self) -> _NullCursor:
        return _NullCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _utc_ts(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


@dataclass(frozen=True)
class ChampionConfig:
    qdrant_url: str
    qdrant_api_key: Optional[str]
    collection: str
    vec_dim: int
    hnsw_ef: int
    hnsw_m: int
    hnsw_ef_construct: int

    @classmethod
    def from_env(cls) -> "ChampionConfig":
        qdrant_url = (os.getenv("QDRANT_URL") or "http://localhost:6333").strip()
        qdrant_api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
        collection = (os.getenv("QUENTIN_QDRANT_COLLECTION") or "quentin_memory").strip()
        try:
            vec_dim = int(os.getenv("MEM_EMBED_DIM", "768"))
        except Exception:
            vec_dim = 768
        try:
            hnsw_ef = int(os.getenv("QUENTIN_QDRANT_HNSW_EF", "128"))
        except Exception:
            hnsw_ef = 128
        try:
            hnsw_m = int(os.getenv("QUENTIN_QDRANT_HNSW_M", "16"))
        except Exception:
            hnsw_m = 16
        try:
            hnsw_ef_construct = int(os.getenv("QUENTIN_QDRANT_HNSW_EF_CONSTRUCT", "100"))
        except Exception:
            hnsw_ef_construct = 100
        return cls(
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection=collection,
            vec_dim=vec_dim,
            hnsw_ef=hnsw_ef,
            hnsw_m=hnsw_m,
            hnsw_ef_construct=hnsw_ef_construct,
        )


class ChampionMemoryStore(MemoryStore):
    """
    Champion backend (B + C + D):
    - B: Postgres is the source-of-truth store for text/metadata; Qdrant is the dense vector index.
    - C: Tiering can be expressed via payload filters (since/tier/kind/importance).
    - D: Sparse retrieval is Postgres FTS; final rerank is in MemoryFabric.

    NOTE: This store aims to be a drop-in for MemoryFabric:
    - vector search: Qdrant
    - text search: Postgres (FTS or ILIKE)
    """

    def __init__(self, *, pg_dsn: Optional[str] = None, use_pgvector: bool = False, cfg: Optional[ChampionConfig] = None):
        self._hot_only = os.getenv("QUENTIN_CHAMPION_HOT_ONLY", "0").strip().lower() in ("1", "true", "yes", "on")
        self.pg: Optional[MemoryStore] = None

        pg_dsn_resolved = (
            (pg_dsn or "").strip()
            or (os.getenv("PG_DSN") or "").strip()
            or (os.getenv("PG_HOST") or "").strip()
        )
        if not self._hot_only and (PostgresMemoryStore is None or not pg_dsn_resolved):
            logger.info(
                "ChampionMemoryStore: Postgres not configured; enabling qdrant hot-only mode."
            )
            self._hot_only = True

        if not self._hot_only:
            if PostgresMemoryStore is None:  # pragma: no cover
                raise RuntimeError("ChampionMemoryStore requires PostgresMemoryStore (psycopg).")
            self.pg = PostgresMemoryStore(dsn=pg_dsn, use_pgvector=use_pgvector)

        self.cfg = cfg or ChampionConfig.from_env()
        self.namespace = (os.getenv("QUENTIN_MEMORY_NAMESPACE") or "default").strip() or "default"
        self._collection = f"{self.cfg.collection}__{self._sanitize_ns(self.namespace)}"
        self.qdrant = QdrantRestClient(
            base_url=self.cfg.qdrant_url,
            api_key=self.cfg.qdrant_api_key,
            timeout_s=float(os.getenv("QUENTIN_QDRANT_TIMEOUT_S", "10") or 10),
        )
        self._fts_enabled = True
        self._vec_ready = False
        self._vector_backend = "qdrant"
        self._vector_math_backend = "remote"
        self._vector_fetch_strategy = "hnsw"
        self._store_vectors_in_pg = os.getenv("QUENTIN_CHAMPION_STORE_VECTORS_IN_PG", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Hot-only mode: Qdrant is the online hot store and carries payload (content + minimal metadata).
        # Postgres becomes optional cold storage (or can be disabled entirely for benchmarks).
        self._hot_policy = (os.getenv("QUENTIN_CHAMPION_HOT_POLICY") or "all").strip().lower()
        try:
            self._hot_recent_days = int(os.getenv("QUENTIN_CHAMPION_HOT_RECENT_DAYS", "90") or 90)
        except Exception:
            self._hot_recent_days = 90
        self._cold_fallback_enable = os.getenv("QUENTIN_CHAMPION_COLD_FALLBACK_ENABLE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if self._hot_only:
            self._cold_fallback_enable = False
        self._reranker = build_reranker()

    def _sanitize_ns(self, ns: str) -> str:
        out = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in (ns or "default"))
        return (out[:64] or "default").strip("_") or "default"

    @property
    def conn(self) -> Any:
        # For MemoryFabric._estimated_total_records() and other compatibility paths.
        if self.pg is None:
            return _NullConn()
        return self.pg.conn

    def init(self) -> None:
        if (not self._hot_only) and self.pg is not None:
            self.pg.init()
        try:
            wait = os.getenv("QUENTIN_QDRANT_WAIT_READY", "1").strip().lower() in ("1", "true", "yes", "on")
            if wait and not self.qdrant.wait_ready(timeout_s=float(os.getenv("QUENTIN_QDRANT_READY_TIMEOUT_S", "30") or 30)):
                raise RuntimeError("Qdrant not ready")
            self.qdrant.ensure_collection(
                name=self._collection,
                dim=self.cfg.vec_dim,
                hnsw_m=self.cfg.hnsw_m,
                hnsw_ef_construct=self.cfg.hnsw_ef_construct,
            )
            self._vec_ready = True
        except Exception as e:
            # Still usable: text-only + optional pgvector fallback.
            logger.warning("ChampionMemoryStore: Qdrant init failed (%s). Vector search will fallback to Postgres.", e)
            self._vec_ready = False

    def _payload(self, record: MemoryRecord) -> Dict[str, Any]:
        # Keep payload small; Postgres remains the source of truth.
        payload: Dict[str, Any] = {
            "tier": record.tier.value,
            "kind": str(record.kind or "episodic"),
            "importance": float(record.importance or 0.0),
            "created_at_ts": _utc_ts(record.created_at) or _utc_ts(now_utc()) or 0,
            "updated_at_ts": _utc_ts(record.updated_at) or _utc_ts(now_utc()) or 0,
            "domain": str((record.domain or record.metadata.get("domain") or "")).strip().lower(),
            "source": str(record.source or ""),
        }
        if self._hot_only:
            payload["content"] = str(record.content or "")
            payload["tags"] = list(record.tags or [])
        return payload

    def _qdrant_filter(self, query: MemoryQuery) -> Optional[Dict[str, Any]]:
        must: List[Dict[str, Any]] = []
        if query.tier:
            must.append({"key": "tier", "match": {"value": query.tier.value}})
        if query.kind:
            must.append({"key": "kind", "match": {"value": str(query.kind)}})
        if query.min_importance and float(query.min_importance) > 0:
            must.append({"key": "importance", "range": {"gte": float(query.min_importance)}})
        if query.since:
            ts = _utc_ts(query.since)
            if ts is not None:
                must.append({"key": "created_at_ts", "range": {"gte": int(ts)}})
        if getattr(query, "domain", None):
            dom = str(getattr(query, "domain", "") or "").strip().lower()
            if dom:
                must.append({"key": "domain", "match": {"value": dom}})
        if not must:
            return None
        return {"must": must}

    def _apply_hot_policy(self, query: MemoryQuery) -> MemoryQuery:
        q = MemoryQuery(**{**query.__dict__})
        p = str(self._hot_policy or "all").strip().lower()
        if p in ("", "all", "none"):
            return q
        if p in ("recent_days", "recent"):
            if q.since is None and int(self._hot_recent_days) > 0:
                q.since = now_utc() - timedelta(days=int(self._hot_recent_days))
            return q
        if p in ("sts_mts", "hot_tiers"):
            # If caller already pins tier, respect it.
            return q
        if p in ("sts_only", "sts"):
            if q.tier is None:
                q.tier = MemoryTier.STS
            return q
        return q

    def _filter_by_hot_tiers(self, records: List[MemoryRecord]) -> List[MemoryRecord]:
        p = str(self._hot_policy or "all").strip().lower()
        if p not in ("sts_mts", "hot_tiers"):
            return records
        hot = {MemoryTier.STS.value, MemoryTier.MTS.value}
        return [r for r in (records or []) if str(getattr(r.tier, "value", "") or "") in hot]

    def _cold_query(self, query: MemoryQuery) -> MemoryQuery:
        q = MemoryQuery(**{**query.__dict__})
        # Cold path should not be restricted by hot recency policy.
        q.since = query.since
        return q

    def _apply_reranker(self, query: MemoryQuery, records: List[MemoryRecord]) -> List[MemoryRecord]:
        if self._reranker is None:
            return records
        qtext = str(getattr(query, "text", "") or "").strip()
        if not qtext:
            return records
        try:
            return self._reranker.rerank(query_text=qtext, records=records, top_k=int(query.top_k))
        except Exception as e:
            logger.warning("ChampionMemoryStore: reranker failed (%s). Keep original order.", e)
            return records

    def add(self, record: MemoryRecord) -> None:
        # Avoid duplicating vectors in Postgres at 1M scale; Qdrant is the vector store.
        self._maybe_upsert_qdrant(record)
        if self._hot_only:
            return
        if self._store_vectors_in_pg and self.pg is not None:
            self.pg.add(record)
        else:
            meta = dict(record.metadata or {})
            meta["_vector_store"] = "qdrant" if (record.vector or []) else "none"
            rec_pg = replace(record, vector=None, metadata=meta)
            if self.pg is not None:
                self.pg.add(rec_pg)

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        if self.pg is None:
            return None
        return self.pg.get(record_id)

    def update(self, record: MemoryRecord) -> None:
        self._maybe_upsert_qdrant(record)
        if self._hot_only:
            return
        if self._store_vectors_in_pg and self.pg is not None:
            self.pg.update(record)
        else:
            meta = dict(record.metadata or {})
            meta["_vector_store"] = "qdrant" if (record.vector or []) else "none"
            rec_pg = replace(record, vector=None, metadata=meta)
            if self.pg is not None:
                self.pg.update(rec_pg)

    def _maybe_upsert_qdrant(self, record: MemoryRecord) -> None:
        if not self._vec_ready:
            return
        vec = record.vector or []
        if not vec:
            return
        if len(vec) != int(self.cfg.vec_dim):
            # Avoid poisoning the collection.
            logger.warning(
                "ChampionMemoryStore: vector dim mismatch for %s (got %s want %s). Skipping qdrant upsert.",
                record.id,
                len(vec),
                self.cfg.vec_dim,
            )
            return
        try:
            self.qdrant.upsert(
                collection=self._collection,
                points=[{"id": str(record.id), "vector": vec, "payload": self._payload(record)}],
                wait=False,
            )
        except Exception as e:
            logger.warning("ChampionMemoryStore: qdrant upsert failed (%s).", e)

    def add_many(self, records: List[MemoryRecord]) -> None:
        recs = list(records or [])
        if not recs:
            return
        if not self._hot_only:
            # 1) Insert into Postgres in one transaction (strip vectors unless explicitly enabled).
            params_list: List[Dict[str, Any]] = []
            for r in recs:
                if self._store_vectors_in_pg:
                    rec_pg = r
                else:
                    meta = dict(r.metadata or {})
                    meta["_vector_store"] = "qdrant" if (r.vector or []) else "none"
                    rec_pg = replace(r, vector=None, metadata=meta)
                params_list.append(self.pg._record_params(rec_pg))  # type: ignore[attr-defined]

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
            sql = f"INSERT INTO memories ({cols}) VALUES ({vals})"
            cur = self.pg.conn.cursor()
            try:
                cur.executemany(sql, params_list)
                self.pg.conn.commit()
            except Exception:
                try:
                    self.pg.conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

        # 2) Upsert into Qdrant in chunks (best-effort; no need to block ingestion if down).
        if not self._vec_ready:
            return
        try:
            batch_size = int(os.getenv("QUENTIN_CHAMPION_QDRANT_UPSERT_BATCH", "256") or 256)
        except Exception:
            batch_size = 256
        batch_size = max(1, min(10_000, int(batch_size)))

        points: List[Dict[str, Any]] = []
        for r in recs:
            vec = r.vector or []
            if not vec:
                continue
            if len(vec) != int(self.cfg.vec_dim):
                continue
            points.append({"id": str(r.id), "vector": vec, "payload": self._payload(r)})

        for i in range(0, len(points), batch_size):
            chunk = points[i : i + batch_size]
            try:
                self.qdrant.upsert(collection=self._collection, points=chunk, wait=False)
            except Exception as e:
                logger.warning("ChampionMemoryStore: qdrant batch upsert failed (%s).", e)
                break

    def _fetch_many_by_ids(self, ids: List[str]) -> List[MemoryRecord]:
        ids = [str(x) for x in (ids or []) if str(x or "").strip()]
        if not ids:
            return []
        # Keep this local to avoid widening the base store API.
        if self.pg is None:
            return []
        cur = self.pg.conn.execute(
            """
            SELECT id, tier, kind, topic, content, created_at, updated_at, source, domain,
                   importance, last_accessed_at, access_count, tags, metadata, consolidated_from_ids,
                   supersedes_ids, relations, update_policy, update_history, decayed
            FROM memories
            WHERE id = ANY(%(ids)s) AND namespace = %(namespace)s AND decayed = FALSE
            """,
            {"ids": ids, "namespace": getattr(self.pg, "namespace", "default")},
        )
        rows = cur.fetchall()
        by_id: Dict[str, MemoryRecord] = {}
        for row in rows:
            rec = self.pg._row_to_record(row)  # type: ignore[attr-defined]
            # Drop vectors for retrieval throughput (fabric doesn't need them for fusion).
            rec.vector = None
            by_id[str(rec.id)] = rec
        return [by_id[x] for x in ids if x in by_id]

    def search(self, query: MemoryQuery) -> List[MemoryRecord]:
        hot_query = self._apply_hot_policy(query)
        # Vector path (dense)
        if hot_query.vector:
            hot_results: List[MemoryRecord] = []
            if self._vec_ready:
                try:
                    pts = self.qdrant.search(
                        collection=self._collection,
                        vector=hot_query.vector,
                        limit=int(hot_query.top_k),
                        qfilter=self._qdrant_filter(hot_query),
                        with_payload=bool(self._hot_only),
                        hnsw_ef=self.cfg.hnsw_ef,
                    )
                    if self._hot_only:
                        out: List[MemoryRecord] = []
                        for p in pts:
                            pl = p.payload or {}
                            tier = MemoryTier.from_str(str(pl.get("tier") or "STS"))
                            created_ts = int(pl.get("created_at_ts") or 0)
                            updated_ts = int(pl.get("updated_at_ts") or 0)
                            created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts > 0 else now_utc()
                            updated_at = datetime.fromtimestamp(updated_ts, tz=timezone.utc) if updated_ts > 0 else created_at
                            rec = MemoryRecord(
                                id=str(p.id),
                                tier=tier,
                                kind=str(pl.get("kind") or "episodic"),
                                content=str(pl.get("content") or ""),
                                created_at=created_at,
                                updated_at=updated_at,
                                source=str(pl.get("source") or "unknown"),
                                domain=str(pl.get("domain") or "") or None,
                                importance=max(float(pl.get("importance") or 0.0), float(p.score or 0.0)),
                                tags=list(pl.get("tags") or []),
                                metadata={"_qdrant_payload": True},
                            )
                            out.append(rec)
                        out = self._filter_by_hot_tiers(out)
                        hot_results = self._apply_reranker(hot_query, out)
                    else:
                        ids = [p.id for p in pts]
                        recs = self._fetch_many_by_ids(ids)
                        # Attach score into importance as a carry signal for downstream fusion.
                        score_by_id = {p.id: float(p.score or 0.0) for p in pts}
                        for r in recs:
                            r.importance = max(float(getattr(r, "importance", 0.0) or 0.0), score_by_id.get(r.id, 0.0))
                        recs = self._filter_by_hot_tiers(recs)
                        hot_results = self._apply_reranker(hot_query, recs)
                    if len(hot_results) >= int(hot_query.top_k):
                        return hot_results[: int(hot_query.top_k)]
                    if self._hot_only:
                        return hot_results[: int(hot_query.top_k)]
                    if not self._cold_fallback_enable:
                        return hot_results[: int(hot_query.top_k)]

                except QdrantError as e:
                    logger.warning("ChampionMemoryStore: qdrant search failed (%s). Falling back to Postgres.", e)
                except Exception as e:
                    logger.warning("ChampionMemoryStore: qdrant search unexpected failure (%s). Falling back.", e)
            # Cold fallback: Postgres pgvector (if enabled) or client-side scoring.
            if self._hot_only:
                return hot_results[: int(hot_query.top_k)]
            if self.pg is None:
                return hot_results[: int(hot_query.top_k)]
            cold = self.pg.search(self._cold_query(query))
            if hot_results:
                by_id = {r.id: r for r in hot_results}
                out = list(hot_results)
                for r in cold:
                    if r.id in by_id:
                        continue
                    out.append(r)
                    if len(out) >= int(hot_query.top_k):
                        break
                return self._apply_reranker(query, out[: int(hot_query.top_k)])
            return self._apply_reranker(query, cold[: int(hot_query.top_k)])

        # Sparse path (text)
        if hot_query.text:
            if self._hot_only:
                return []
            if self.pg is None:
                return []
            if (hot_query.text_mode or "").lower() == "fts":
                try:
                    scored = self.pg.search_text_with_scores(hot_query)  # type: ignore[attr-defined]
                    out = [r for r, _ in scored]
                    # Carry FTS score into importance for fusion.
                    for (r, s) in scored:
                        r.importance = max(float(getattr(r, "importance", 0.0) or 0.0), float(s or 0.0))
                    out = self._filter_by_hot_tiers(out)
                    if len(out) >= int(hot_query.top_k) or not self._cold_fallback_enable:
                        return self._apply_reranker(hot_query, out[: int(hot_query.top_k)])
                    cold_scored = self.pg.search_text_with_scores(self._cold_query(query))  # type: ignore[attr-defined]
                    by_id = {r.id for r in out}
                    for r, _s in cold_scored:
                        if r.id in by_id:
                            continue
                        out.append(r)
                        if len(out) >= int(hot_query.top_k):
                            break
                    return self._apply_reranker(query, out[: int(hot_query.top_k)])
                except Exception as e:
                    logger.warning("ChampionMemoryStore: FTS search failed (%s). Falling back to LIKE.", e)
                    q2 = MemoryQuery(**{**hot_query.__dict__, "text_mode": "like"})
                    out = self.pg.search(q2)
                    out = self._filter_by_hot_tiers(out)
                    return self._apply_reranker(hot_query, out[: int(hot_query.top_k)])
            out = self.pg.search(hot_query)
            out = self._filter_by_hot_tiers(out)
            if len(out) >= int(hot_query.top_k) or not self._cold_fallback_enable:
                return self._apply_reranker(hot_query, out[: int(hot_query.top_k)])
            cold = self.pg.search(self._cold_query(query))
            by_id = {r.id for r in out}
            for r in cold:
                if r.id in by_id:
                    continue
                out.append(r)
                if len(out) >= int(hot_query.top_k):
                    break
            return self._apply_reranker(query, out[: int(hot_query.top_k)])

        # Default
        if self._hot_only:
            return []
        if self.pg is None:
            return []
        out = self.pg.search(hot_query)
        out = self._filter_by_hot_tiers(out)
        return out[: int(hot_query.top_k)]

    def promote(self, record_id: str, to_tier: MemoryTier) -> None:
        if (not self._hot_only) and self.pg is not None:
            self.pg.promote(record_id, to_tier)
            # Best-effort payload update (skip if qdrant down).
            rec = self.pg.get(record_id)
            if rec:
                self._maybe_upsert_qdrant(rec)

    def mark_decayed(self, record_id: str) -> None:
        if (not self._hot_only) and self.pg is not None:
            self.pg.mark_decayed(record_id)
        if self._vec_ready:
            try:
                self.qdrant.delete_points(collection=self._collection, ids=[str(record_id)], wait=False)
            except Exception:
                pass

    def get_candidates_for_consolidation(self, tier: MemoryTier, limit: int = 100) -> List[MemoryRecord]:
        if self._hot_only or self.pg is None:
            return []
        return self.pg.get_candidates_for_consolidation(tier=tier, limit=limit)

    def touch_access_many(self, record_ids: List[str], at: datetime) -> None:
        # Keep the source-of-truth in Postgres. Payload updates are optional and can lag.
        if self._hot_only or self.pg is None:
            return
        return self.pg.touch_access_many(record_ids, at)

    def cleanup_namespace(self, *, drop_collection: bool = False) -> Dict[str, Any]:
        """
        Best-effort cleanup for benchmark namespaces.
        """
        out: Dict[str, Any] = {
            "namespace": self.namespace,
            "collection": self._collection,
            "pg_deleted": 0,
            "collection_deleted": False,
            "status": "ok",
        }
        if not self._hot_only:
            try:
                cur = self.pg.conn.execute(
                    "DELETE FROM memories WHERE namespace = %(namespace)s",
                    {"namespace": self.namespace},
                )
                out["pg_deleted"] = int(getattr(cur, "rowcount", 0) or 0)
                self.pg.conn.commit()
            except Exception as e:
                try:
                    self.pg.conn.rollback()
                except Exception:
                    pass
                out["status"] = "partial"
                out["pg_error"] = str(e)

        if drop_collection:
            try:
                self.qdrant.delete_collection(self._collection)
                out["collection_deleted"] = True
            except Exception as e:
                out["status"] = "partial"
                out["qdrant_error"] = str(e)
        return out
