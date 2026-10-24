from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from quentin.traces.core import TraceRecorder, TraceEventType, new_trace_event
from quentin.utils.time import now_utc
from quentin.config.memory_runtime import MemoryRuntimeConfig
from quentin.infra.llm.embeddings import EmbeddingClient, create_embedding_client_from_env
from quentin.knowledge_graph.service import GraphService
from quentin.knowledge_graph.builders.relations_sync import RelationsSyncBuilder
from quentin.knowledge_graph.builders.extraction import GraphKnowledgeExtractor
from quentin.knowledge_graph.schema import NodeType

from .models import MemoryQuery, MemoryRecord, MemoryTier, MemoryUpdatePolicy
from .embedding_batch import resolve_batch_manager, fingerprint_header_names
from .recall_defaults import load_memory_recall_defaults
from .session_files import build_session_delta, session_path_for_file
from .code_fingerprint import build_code_function_fingerprints, build_function_fingerprint_hash
from .store_base import MemoryStore
from .store_sqlite import SqliteMemoryStore
from .search_manager import ParallelSearchManager, SearchManagerConfig, SessionSearchSpec

try:
    from .store_postgres import PostgresMemoryStore
except Exception:
    PostgresMemoryStore = None  # type: ignore

try:
    from .store_sqlite_vec import SqliteVecMemoryStore
except Exception:
    SqliteVecMemoryStore = None  # type: ignore

logger = logging.getLogger(__name__)


class MemoryFabric:
    """
    高层封装：提供简单 API，给 loops / runtime 用。
    """

    def __init__(
        self,
        repo_root: str | Path = ".",
        db_path: str | Path | None = None,
        use_postgres: bool | None = None,
        use_pgvector: bool = True,
        trace_recorder: Optional[TraceRecorder] = None,
        trace_id: str = "memory-fabric",
        store: Optional[MemoryStore] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        **_compat: Any,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.runtime_config = MemoryRuntimeConfig.from_env()
        
        override = (os.getenv("QUENTIN_MEMORY_RECALL_DEFAULTS_PATH") or "").strip()
        if override:
            self._recall_defaults_path = Path(override).expanduser().resolve()
        else:
            self._recall_defaults_path = self.repo_root / "config" / "memory_recall_config.json"
        self._recall_defaults_cached = None
        self._recall_defaults_mtime = None

        # Back-compat: old call sites used `use_postgres=`; keep it accepted.
        _ = (use_postgres, use_pgvector, _compat)

        # Store backend: injected store wins; otherwise default to SQLite (Vec if available, else standard).
        if store is not None:
            self.store = store
            # Call init() for injected stores as well; Container injects an uninitialized store.
            try:
                self.store.init()
            except Exception:
                pass
        else:
            store_kind = (os.getenv("QUENTIN_MEMORY_STORE") or "").strip().lower()
            store_selected = False

            # Allow env-selected backends even when MemoryFabric is used directly (bench/scripts),
            # not only through Container injection.
            if store_kind == "champion":
                try:
                    from .store_champion import ChampionMemoryStore

                    dsn = os.getenv("PG_DSN") or self._guess_pg_dsn()
                    self.store = ChampionMemoryStore(pg_dsn=dsn)
                    self.store.init()
                    store_selected = True
                except Exception as e:
                    logger.warning("MemoryFabric: failed to init ChampionMemoryStore (%s), falling back to SQLite", e)
                    store_selected = False

            if (not store_selected) and store_kind == "postgres" and PostgresMemoryStore is not None:
                try:
                    dsn = os.getenv("PG_DSN") or self._guess_pg_dsn()
                    self.store = PostgresMemoryStore(dsn=dsn, use_pgvector=bool(use_pgvector))
                    self.store.init()
                    store_selected = True
                except Exception as e:
                    logger.warning("MemoryFabric: failed to init PostgresMemoryStore (%s), falling back to SQLite", e)
                    store_selected = False

            if (not store_selected) and store_kind in ("sqlite", "sqlite_vec"):
                # Honor explicit selection (useful for tests/bench).
                raw_db_path = db_path if db_path is not None else (self.repo_root / "data" / "memory.db")
                path = (
                    Path(raw_db_path)
                    if str(raw_db_path).strip() not in {":memory:", "file::memory:"}
                    else raw_db_path
                )
                if store_kind == "sqlite_vec" and SqliteVecMemoryStore is not None and isinstance(path, Path):
                    try:
                        self.store = SqliteVecMemoryStore(path)
                        self.store.init()
                        logger.info("MemoryFabric: using optimized SqliteVecMemoryStore (env selected)")
                        store_selected = True
                    except Exception as e:
                        logger.warning(
                            "MemoryFabric: failed to init SqliteVecMemoryStore (%s), falling back to standard SQLite",
                            e,
                        )
                        self.store = SqliteMemoryStore(path)
                        self.store.init()
                        store_selected = True
                else:
                    self.store = SqliteMemoryStore(path)  # type: ignore[arg-type]
                    self.store.init()
                    store_selected = True

            if store_selected:
                # Backend chosen; skip default path selection.
                pass
            else:
                raw_db_path = db_path if db_path is not None else (self.repo_root / "data" / "memory.db")
                # Unit-test / ephemeral mode: default to the standard store so vector dims can vary freely.
                # sqlite-vec requires a fixed embedding dimension and will reject mismatched vectors.
                if str(raw_db_path).strip() in {":memory:", "file::memory:"}:
                    self.store = SqliteMemoryStore(raw_db_path)  # type: ignore[arg-type]
                    self.store.init()
                else:
                    path = Path(raw_db_path)
                    # Try to use SqliteVecMemoryStore first (Phase 2 Upgrade)
                    if SqliteVecMemoryStore is not None:
                        try:
                            self.store = SqliteVecMemoryStore(path)
                            self.store.init()
                            logger.info("MemoryFabric: using optimized SqliteVecMemoryStore")
                        except Exception as e:
                            logger.warning(
                                f"MemoryFabric: failed to init SqliteVecMemoryStore ({e}), falling back to standard SQLite"
                            )
                            self.store = SqliteMemoryStore(path)
                            self.store.init()
                    else:
                        self.store = SqliteMemoryStore(path)
                        self.store.init()
        
        # 2. Setup Embedding Client
        self.embedding_client = embedding_client or create_embedding_client_from_env()
        self.embedding_batcher = self._build_embedding_batcher()
        
        # 3. Setup Knowledge Graph Service (Phase 4)
        from quentin.memory.knowledge_graph import SimpleKnowledgeGraph
        self.kg = None
        try:
            self.kg = SimpleKnowledgeGraph(str(self.repo_root))
        except Exception as e:
            logger.warning(f"Failed to initialize Knowledge Graph: {e}")
        
        # Mapping legacy names used in other surgeries
        self.graph_builder = self.kg 
        self.graph_service = self.kg
        self.graph_extractor = None
        try:
            self.graph_extractor = GraphKnowledgeExtractor()
        except Exception:
            self.graph_extractor = None
        
        self.trace_recorder = trace_recorder
        self.trace_id = trace_id
        self._embedding_hash_cache: Dict[str, List[float]] = {}
        self._session_file_offsets: Dict[str, int] = {}
        self._memory_sync_write_lock = threading.Lock()
        self._warned_text_index_gap = False
        self._cached_total_records_at = 0.0
        self._cached_total_records_val = 0
        self._pre_search_sync_hook: Optional[Callable[[MemoryQuery], Dict[str, Any]]] = None
        self._parallel_search_manager = ParallelSearchManager(
            config=SearchManagerConfig(
                max_workers=max(1, int(self.runtime_config.search_concurrency)),
                per_session_timeout_s=max(0.1, float(self.runtime_config.search_timeout_s)),
                rerank_enabled=bool(self.runtime_config.rerank_enabled),
                rerank_time_half_life_hours=float(self.runtime_config.rerank_time_half_life_hours),
                source_priors={
                    "session_delta:": float(self.runtime_config.source_prior_session_delta),
                    "session_file:": float(self.runtime_config.source_prior_session_file),
                    "memory_file:": float(self.runtime_config.source_prior_memory_file),
                },
                domain_match_bonus=float(self.runtime_config.domain_prior_match),
                max_sessions_scanned=int(getattr(self.runtime_config, "search_max_sessions_scanned", 0) or 0),
                max_candidates_reranked=int(getattr(self.runtime_config, "search_max_candidates_reranked", 0) or 0),
                adaptive_degrade_enabled=bool(
                    getattr(self.runtime_config, "search_adaptive_degrade_enabled", True)
                ),
                timeout_pressure_threshold=float(
                    getattr(self.runtime_config, "search_timeout_pressure_threshold", 0.4)
                ),
                adaptive_session_cap_factor=int(
                    getattr(self.runtime_config, "search_adaptive_session_cap_factor", 3)
                ),
            )
        )
        
        # P5: Surgery Thirty-five - Model Consistency Guard (OpenClaw Parity)
        self._ensure_model_consistency()

    def set_pre_search_sync_hook(self, hook: Optional[Callable[[MemoryQuery], Dict[str, Any]]]) -> None:
        self._pre_search_sync_hook = hook

    def _run_pre_search_sync_hook(self, query: MemoryQuery) -> Dict[str, Any]:
        hook = self._pre_search_sync_hook
        if hook is None:
            return {"status": "skipped"}
        try:
            # Prefer keyword call to support hooks that declare `*, query=...` (MemoryManager),
            # but keep a positional fallback for legacy call sites.
            try:
                out = hook(query=query)  # type: ignore[misc]
            except TypeError:
                out = hook(query)  # type: ignore[misc]
            if isinstance(out, dict):
                return out
            return {"status": "ok"}
        except Exception as e:
            logger.warning("MemoryFabric: pre-search sync hook failed: %s", e)
            return {"status": "error", "error": str(e)}

    def _lookup_embedding_cache(self, content_hash: str, model_name: str) -> Optional[List[float]]:
        key = f"{model_name}:{content_hash}"
        v = self._embedding_hash_cache.get(key)
        return list(v) if v else None

    def _save_to_embedding_cache(self, content_hash: str, vector: List[float], model_name: str) -> None:
        key = f"{model_name}:{content_hash}"
        self._embedding_hash_cache[key] = list(vector or [])

    def _build_embedding_batcher(self):
        provider = "unknown"
        model = "unknown"
        try:
            cfg = getattr(self.embedding_client, "_cfg", None)
            if cfg is not None:
                provider = str(getattr(cfg, "provider", provider) or provider)
                model = str(getattr(cfg, "model", model) or model)
            else:
                provider = str(getattr(self.embedding_client, "provider", provider) or provider)
                model = str(getattr(self.embedding_client, "model_name", model) or model)
        except Exception:
            pass

        cache_enabled = os.getenv("QUENTIN_MEMORY_EMBED_CACHE_ENABLE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        cache_path = os.getenv(
            "QUENTIN_MEMORY_EMBED_CACHE_PATH",
            str(self.repo_root / "data" / "embedding_cache.sqlite"),
        )
        try:
            timeout_s = float(os.getenv("MEM_EMBED_TIMEOUT", "20"))
        except Exception:
            timeout_s = 20.0
        try:
            batch_size = int(os.getenv("MEM_EMBED_BATCH_SIZE", "128"))
        except Exception:
            batch_size = 128
        try:
            retry_max_attempts = int(os.getenv("MEM_EMBED_RETRY_MAX_ATTEMPTS", "3"))
        except Exception:
            retry_max_attempts = 3
        try:
            retry_base_delay_ms = int(os.getenv("MEM_EMBED_RETRY_BASE_DELAY_MS", "300"))
        except Exception:
            retry_base_delay_ms = 300
        try:
            retry_max_delay_ms = int(os.getenv("MEM_EMBED_RETRY_MAX_DELAY_MS", "2000"))
        except Exception:
            retry_max_delay_ms = 2000
        async_batch_enabled = os.getenv("MEM_EMBED_OPENAI_ASYNC_BATCH", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        async_batch_wait = os.getenv("MEM_EMBED_OPENAI_ASYNC_WAIT", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        try:
            async_poll_s = float(os.getenv("MEM_EMBED_OPENAI_ASYNC_POLL_S", "2"))
        except Exception:
            async_poll_s = 2.0
        try:
            async_timeout_s = float(os.getenv("MEM_EMBED_OPENAI_ASYNC_TIMEOUT_S", "120"))
        except Exception:
            async_timeout_s = 120.0
        gemini_async_enabled = os.getenv("MEM_EMBED_GEMINI_ASYNC_BATCH", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        gemini_async_wait = os.getenv("MEM_EMBED_GEMINI_ASYNC_WAIT", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        try:
            gemini_poll_s = float(os.getenv("MEM_EMBED_GEMINI_ASYNC_POLL_S", "2"))
        except Exception:
            gemini_poll_s = 2.0
        try:
            gemini_timeout_s = float(os.getenv("MEM_EMBED_GEMINI_ASYNC_TIMEOUT_S", "120"))
        except Exception:
            gemini_timeout_s = 120.0
        try:
            account_tier = int(os.getenv("MEM_EMBED_ACCOUNT_TIER", "1"))
        except Exception:
            account_tier = 1
        try:
            batch_concurrency = int(os.getenv("MEM_EMBED_BATCH_CONCURRENCY", "0"))
        except Exception:
            batch_concurrency = 0

        return resolve_batch_manager(
            embedding_client=self.embedding_client,
            provider=provider,
            model=model,
            provider_key=self._compute_embedding_provider_key(provider=provider, model=model),
            cache_path=cache_path,
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            timeout_s=timeout_s,
            batch_size=batch_size,
            openai_async_batch_enabled=async_batch_enabled,
            openai_async_batch_wait=async_batch_wait,
            openai_async_poll_interval_s=async_poll_s,
            openai_async_timeout_s=async_timeout_s,
            gemini_base_url=os.getenv(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            ),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_async_batch_enabled=gemini_async_enabled,
            gemini_async_batch_wait=gemini_async_wait,
            gemini_async_poll_interval_s=gemini_poll_s,
            gemini_async_timeout_s=gemini_timeout_s,
            account_tier=account_tier,
            batch_concurrency=batch_concurrency,
            retry_max_attempts=retry_max_attempts,
            retry_base_delay_ms=retry_base_delay_ms,
            retry_max_delay_ms=retry_max_delay_ms,
            job_store_path=cache_path,
            enable_cache=cache_enabled,
        )

    def _compute_embedding_provider_key(self, *, provider: str, model: str) -> str:
        base_url = ""
        header_names: List[str] = []
        if provider == "openai":
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
            header_names = fingerprint_header_names({"Authorization": "", "Content-Type": "application/json"})
        elif provider == "gemini":
            base_url = os.getenv(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            ).strip()
            header_names = fingerprint_header_names({"x-goog-api-key": "", "Content-Type": "application/json"})
        key_raw = f"{provider}|{model}|{base_url}|{','.join(header_names)}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    def _ensure_model_consistency(self) -> None:
        """
        P5: Detects if the embedding model has changed.
        If yes, the entire index is invalidated to prevent dimension mismatch.
        """
        if not hasattr(self.store, "conn"): return
        
        current_model = self.embedding_client.model_name if hasattr(self.embedding_client, "model_name") else "unknown"
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return

        # sqlite and postgres use different SQL dialects; keep this guard best-effort.
        def _rollback() -> None:
            try:
                conn.rollback()
            except Exception:
                return

        # 1) Try sqlite dialect first.
        try:
            cur = conn.execute("SELECT value FROM meta WHERE key = 'embedding_model'")
            row = cur.fetchone()
            indexed_model = row["value"] if row else None

            if indexed_model and indexed_model != current_model:
                logger.warning(
                    "MemoryFabric: Model mismatch! Indexed=%s, Current=%s. RE-INDEXING...",
                    indexed_model,
                    current_model,
                )
                self.reindex_indexes()

            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('embedding_model', ?)",
                (current_model,),
            )
            conn.commit()
            return
        except Exception:
            _rollback()

        # 2) Postgres dialect fallback.
        try:
            cur = conn.execute("SELECT value FROM meta WHERE key = %s", ("embedding_model",))
            row = cur.fetchone()
            indexed_model = row["value"] if row else None

            if indexed_model and indexed_model != current_model:
                logger.warning(
                    "MemoryFabric: Model mismatch! Indexed=%s, Current=%s. RE-INDEXING...",
                    indexed_model,
                    current_model,
                )
                self.reindex_indexes()

            conn.execute(
                """
                INSERT INTO meta (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                ("embedding_model", current_model),
            )
            conn.commit()
        except Exception as e:
            _rollback()
            logger.error("MemoryFabric: Model consistency check failed: %s", e)

    def _ensure_file_fingerprint_cache_table(self) -> None:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_fingerprint_cache (
                    file_path TEXT PRIMARY KEY,
                    function_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        except Exception:
            pass

    def _ensure_memory_file_sync_cache_table(self) -> None:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_file_sync_cache (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        except Exception:
            pass

    def _get_memory_file_content_hash(self, file_path: str) -> str:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return ""
        self._ensure_memory_file_sync_cache_table()
        try:
            row = conn.execute(
                "SELECT content_hash FROM memory_file_sync_cache WHERE file_path = ?",
                (str(file_path),),
            ).fetchone()
            if not row:
                return ""
            if isinstance(row, dict):
                return str(row.get("content_hash") or "")
            return str(row["content_hash"] or "")
        except Exception:
            return ""

    def _set_memory_file_content_hash(self, file_path: str, content_hash: str) -> None:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return
        self._ensure_memory_file_sync_cache_table()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_file_sync_cache(file_path, content_hash, updated_at)
                VALUES(?, ?, ?)
                """,
                (str(file_path), str(content_hash or ""), now_utc().isoformat()),
            )
            conn.commit()
        except Exception:
            pass

    def _remove_memory_file_content_hash(self, file_path: str) -> None:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return
        self._ensure_memory_file_sync_cache_table()
        try:
            conn.execute("DELETE FROM memory_file_sync_cache WHERE file_path = ?", (str(file_path),))
            conn.commit()
        except Exception:
            pass

    def _list_memory_markdown_files(self, *, workspace_dir: Optional[str | Path] = None) -> List[Path]:
        base = Path(workspace_dir).resolve() if workspace_dir is not None else self.repo_root
        out: List[Path] = []
        for name in ("MEMORY.md", "memory.md"):
            p = base / name
            if p.exists() and p.is_file():
                out.append(p.resolve())
        mem_dir = base / "memory"
        if mem_dir.exists() and mem_dir.is_dir():
            out.extend(sorted(p.resolve() for p in mem_dir.rglob("*.md") if p.is_file()))
        # stable de-dupe
        dedup: List[Path] = []
        seen: Set[str] = set()
        for p in out:
            s = str(p)
            if s in seen:
                continue
            seen.add(s)
            dedup.append(p)
        return dedup

    def _cleanup_stale_memory_file_records(self, *, active_paths: Set[str], source_prefix: str) -> int:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return 0
        self._ensure_memory_file_sync_cache_table()
        deleted = 0
        try:
            rows = conn.execute("SELECT file_path FROM memory_file_sync_cache").fetchall()
            for row in rows:
                p = str((row["file_path"] if not isinstance(row, dict) else row.get("file_path")) or "")
                if not p or p in active_paths:
                    continue
                src = f"{source_prefix}:{p}"
                conn.execute("DELETE FROM memories WHERE source = ?", (src,))
                conn.execute("DELETE FROM memory_file_sync_cache WHERE file_path = ?", (p,))
                self._remove_memory_file_content_hash(p)
                self._set_cached_file_function_hash(p, "")
                deleted += 1
            conn.commit()
        except Exception:
            pass
        return deleted

    def _get_cached_file_function_hash(self, file_path: str) -> str:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return ""
        self._ensure_file_fingerprint_cache_table()
        try:
            row = conn.execute(
                "SELECT function_hash FROM file_fingerprint_cache WHERE file_path = ?",
                (str(file_path),),
            ).fetchone()
            if not row:
                return ""
            if isinstance(row, dict):
                return str(row.get("function_hash") or "")
            return str(row["function_hash"] or "")
        except Exception:
            return ""

    def _set_cached_file_function_hash(self, file_path: str, function_hash: str) -> None:
        conn = getattr(self.store, "conn", None)
        if conn is None:
            return
        self._ensure_file_fingerprint_cache_table()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO file_fingerprint_cache(file_path, function_hash, updated_at)
                VALUES(?, ?, ?)
                """,
                (str(file_path), str(function_hash or ""), now_utc().isoformat()),
            )
            conn.commit()
        except Exception:
            pass

    def _get_recall_defaults(self) -> Optional[object]:
        try:
            p = self._recall_defaults_path
            if not p.exists():
                self._recall_defaults_cached = None
                self._recall_defaults_mtime = None
                return None
            mtime = p.stat().st_mtime
            if self._recall_defaults_cached is not None and self._recall_defaults_mtime == mtime:
                return self._recall_defaults_cached
            defaults = load_memory_recall_defaults(p)
            self._recall_defaults_cached = defaults
            self._recall_defaults_mtime = mtime
            return defaults
        except Exception:
            return None

    def _record_trace(self, action: str, payload: Dict[str, Any]) -> None:
        if not self.trace_recorder:
            return
        event = new_trace_event(
            trace_id=self.trace_id,
            event_type=TraceEventType.MEMORY,
            payload={"action": action, **payload},
        )
        try:
            self.trace_recorder.record_event(event)
        except Exception:
            logger.exception("MemoryFabric: failed to record trace event %s", action)

    def _finalize_recall(
        self,
        query: MemoryQuery,
        records: List[MemoryRecord],
        *,
        mode: str,
        use_vector: bool,
        latency_ms: Optional[float] = None,
        debug_payload: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryRecord]:
        records = self._rerank_by_query_alignment(records=records, query=query, mode=mode)
        now = now_utc()
        writeback_enabled = os.getenv("QUENTIN_MEMORY_RECALL_WRITEBACK_ENABLE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        try:
            writeback_max_updates = int(os.getenv("QUENTIN_MEMORY_RECALL_WRITEBACK_MAX_UPDATES", "5"))
        except Exception:
            writeback_max_updates = 5
        writeback_max_updates = max(0, writeback_max_updates)

        ids_to_touch: List[str] = []
        for idx, rec in enumerate(records):
            if not writeback_enabled:
                continue
            if writeback_max_updates > 0 and idx >= writeback_max_updates:
                continue
            rec.last_accessed_at = now
            rec.access_count += 1
            ids_to_touch.append(str(rec.id))
        if ids_to_touch:
            try:
                self.store.touch_access_many(ids_to_touch, now)
            except Exception:
                logger.exception("MemoryFabric: failed to touch access stats for %s records", len(ids_to_touch))

        payload: Dict[str, Any] = {
            "query_text": query.text,
            "mode": mode,
            "use_vector": use_vector,
            "result_count": len(records),
            "top_ids": [r.id for r in records[:3]],
        }
        source_counts: Dict[str, int] = {}
        for rec in records:
            src = str(getattr(rec, "source", "") or "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
        if source_counts:
            payload["source_counts"] = source_counts
            payload["top_sources"] = sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        if getattr(query, "tier", None) is not None:
            try:
                payload["query_tier"] = query.tier.value  # type: ignore[attr-defined]
            except Exception:
                payload["query_tier"] = str(getattr(query, "tier"))
        if getattr(query, "kind", None) is not None:
            payload["query_kind"] = query.kind
        if getattr(query, "domain", None) is not None:
            payload["query_domain"] = query.domain
        payload["include_cross_domain"] = bool(getattr(query, "include_cross_domain", True))
        if latency_ms is not None:
            payload["latency_ms"] = float(latency_ms)
        if debug_payload:
            payload.update(debug_payload)
        self._record_trace("recall", payload)
        return records

    def _prefer_fts_for_online_text(self) -> bool:
        prefer = os.getenv("QUENTIN_MEMORY_TEXT_PREFER_FTS", "1").strip().lower() in ("1", "true", "yes", "on")
        if not prefer:
            return False
        store_fts = bool(getattr(self.store, "_fts_enabled", False))
        if not store_fts:
            return False
        try:
            min_records = int(os.getenv("QUENTIN_MEMORY_TEXT_FTS_MIN_RECORDS", "5000"))
        except Exception:
            min_records = 5000
        if min_records <= 0:
            return True
        return self._estimated_total_records() >= int(min_records)

    def _estimated_total_records(self) -> int:
        now_t = time.time()
        # Cache short-term to avoid extra count query on every recall.
        if (now_t - float(self._cached_total_records_at)) <= 10.0:
            return int(self._cached_total_records_val)
        try:
            if hasattr(self.store, "conn"):
                conn = self.store.conn
                try:
                    cur = conn.execute("SELECT COUNT(*) AS c FROM memories WHERE decayed = 0")
                except Exception:
                    # Important: on Postgres, a failed statement aborts the transaction until rollback().
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    cur = conn.execute("SELECT COUNT(*) AS c FROM memories WHERE decayed = FALSE")
                row = cur.fetchone()
                val = int((row["c"] if row and "c" in row.keys() else 0) or 0)
                self._cached_total_records_val = val
                self._cached_total_records_at = now_t
                return val
        except Exception:
            pass
        return int(self._cached_total_records_val or 0)

    def _run_text_query_with_fallback(self, query: MemoryQuery) -> tuple[List[MemoryRecord], bool]:
        used_fts = False
        q = MemoryQuery(**{**query.__dict__})
        if self._prefer_fts_for_online_text():
            q.text_mode = "fts"
            strict = self._build_fts_query(str(getattr(q, "text", "") or ""))
            if strict:
                q.text = strict
            out = self.store.search(q)
            used_fts = True
            if out:
                return out, used_fts
            # Compatibility fallback: keep behavior if FTS query is too strict.
            q.text_mode = "like"
            return self.store.search(q), used_fts
        return self.store.search(q), used_fts

    def _apply_online_active_window(self, query: MemoryQuery) -> MemoryQuery:
        q = MemoryQuery(**{**query.__dict__})
        if getattr(q, "since", None) is not None:
            return q
        enabled = os.getenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_ENABLE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not enabled:
            return q
        try:
            min_records = int(os.getenv("QUENTIN_MEMORY_ONLINE_OFFLINE_THRESHOLD", "300000"))
        except Exception:
            min_records = 300000
        if self._estimated_total_records() < max(1, int(min_records)):
            return q
        try:
            days = int(os.getenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_DAYS", "90"))
        except Exception:
            days = 90
        if days <= 0:
            return q
        q.since = now_utc() - timedelta(days=int(days))
        return q

    def _maybe_warn_text_index_gap(self) -> None:
        if self._warned_text_index_gap:
            return
        try:
            threshold = int(os.getenv("QUENTIN_MEMORY_TEXT_INDEX_WARN_THRESHOLD", "50000"))
        except Exception:
            threshold = 50000
        if threshold <= 0:
            return
        total = self._estimated_total_records()
        has_fts = bool(getattr(self.store, "_fts_enabled", False))
        has_vec = bool(getattr(self.store, "_vec_ready", False))
        if total >= threshold and (not has_fts) and (not has_vec):
            logger.warning(
                "MemoryFabric: large corpus without FTS/sqlite-vec (%s records). Enable QUENTIN_MEMORY_FTS=1 and/or sqlite-vec.",
                total,
            )
            self._warned_text_index_gap = True

    def _rerank_by_query_alignment(
        self,
        *,
        records: List[MemoryRecord],
        query: MemoryQuery,
        mode: str,
    ) -> List[MemoryRecord]:
        enabled = os.getenv("QUENTIN_MEMORY_QUERY_RERANK_ENABLE", "1").strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return records
        if mode not in ("text_only", "hybrid"):
            return records
        qtext = str(getattr(query, "text", "") or "").strip().lower()
        if not qtext:
            return records
        tokens = [t for t in re.split(r"[^A-Za-z0-9_]+", qtext) if (len(t) >= 2 or t.isdigit())]
        if not tokens:
            return records

        query_domain = str(getattr(query, "domain", "") or "").strip().lower()
        scored: List[tuple[float, int, MemoryRecord]] = []
        for idx, rec in enumerate(records):
            content = str(getattr(rec, "content", "") or "").lower()
            if not content:
                scored.append((0.0, idx, rec))
                continue
            exact_phrase = 1.0 if qtext in content else 0.0
            overlap = sum(1 for t in tokens if t in content) / float(len(tokens))
            dom = str(getattr(rec, "domain", "") or "").strip().lower()
            domain_bonus = 0.2 if (query_domain and dom == query_domain) else 0.0
            # Prefer explicit lexical alignment first, keep small original-rank prior for stability.
            score = (2.0 * exact_phrase) + (1.0 * overlap) + domain_bonus - (idx * 1e-3)
            scored.append((score, idx, rec))
        scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
        return [rec for _, _, rec in scored]

    def _score_text(self, query_text: Optional[str], content: str) -> float:
        if not query_text:
            return 0.0
        keywords = [k for k in re.split(r"\W+", query_text.lower()) if k]
        if not keywords:
            return 0.0
        hay = (content or "").lower()
        hits = sum(1 for k in keywords if k in hay)
        return hits / float(len(keywords))

    def _score_vector(self, query_vector: List[float], record_vector: List[float]) -> Optional[float]:
        if not query_vector or not record_vector:
            return None
        if len(query_vector) != len(record_vector):
            return None
        qnorm = math.sqrt(sum(x * x for x in query_vector)) or 1.0
        rnorm = math.sqrt(sum(x * x for x in record_vector)) or 1.0
        dot = sum(a * b for a, b in zip(query_vector, record_vector))
        cosine = dot / (qnorm * rnorm)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    def warm_session(self, session_id: str) -> None:
        """
        P5: Ported from OpenClaw's 'warmSession'.
        Proactively indexes session history to reduce latency of first search.
        """
        logger.info(f"MemoryFabric: Warming session {session_id}...")
        from quentin.infra.sessions.dirty_sync import dirty_sync
        
        # Force a sync to clear any pending history into the memory index
        try:
            # We don't want to block the entire loop startup, but we want 
            # to start the background sync immediately.
            dirty_sync.track_change(session_id, {"warm_up": True})
        except Exception as e:
            logger.warning(f"MemoryFabric: Failed to warm session {session_id}: {e}")

    # ---- high-level APIs ----

    def remember_atomic(
        self,
        content: str,
        source: str,
        tier: MemoryTier = MemoryTier.STS,
        domain: Optional[str] = None,
        topic: Optional[str] = None,
        importance: float = 0.0,
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
        vector: Optional[List[float]] = None,
        kind: str = "episodic",
        relations: Optional[Dict[str, float]] = None,
        consolidated_from_ids: Optional[List[str]] = None,
        update_policy: Optional[Dict[str, Any]] = None,
    ) -> MemoryRecord:
        # P5: Surgery Forty-six - Credential Scrubbing (OpenClaw Parity)
        from quentin.infra.security.scrubber import CredentialScrubber
        content = CredentialScrubber.scrub_text(content)
        metadata = CredentialScrubber.scrub_data(metadata or {})
        
        meta = dict(metadata)
        
        # ---------------------------------------------------------
        # Phase 1: Embedding Injection
        # ---------------------------------------------------------
        vector_status = "provided" if vector else "skipped"
        
        if vector is None and self.embedding_client:
            # P5: Surgery One Hundred and Six - Embedding Cache lookup (OpenClaw Parity)
            import hashlib
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            model_name = getattr(self.embedding_client, "model_name", "unknown")
            
            cached_vector = self._lookup_embedding_cache(content_hash, model_name)
            if cached_vector:
                vector = cached_vector
                vector_status = "cache_hit"
                meta["cached"] = True
            else:
                try:
                    start_t = time.perf_counter()
                    generated_vector = self.embedding_batcher.embed_text(content)
                    duration_ms = (time.perf_counter() - start_t) * 1000
                    
                    if generated_vector:
                        vector = generated_vector
                        vector_status = "generated"
                        meta["embed_ms"] = int(duration_ms)
                        # Save to cache for physical speedup
                        self._save_to_embedding_cache(content_hash, vector, model_name)
                    else:
                        vector_status = "disabled_or_empty"
                        
                except Exception as e:
                    logger.warning(f"MemoryFabric: auto-embedding failed: {e}")
                    vector_status = "failed"
                    meta["embed_error"] = str(e)
        
        meta["vector_status"] = vector_status
        # ---------------------------------------------------------

        rec = MemoryRecord.new(
            tier=tier,
            content=content,
            source=source,
            domain=domain,
            topic=topic,
            importance=importance,
            tags=tags,
            metadata=meta,
            consolidated_from_ids=consolidated_from_ids,
            vector=vector,
            kind=kind,
            relations=relations,
            update_policy=None,
        )
        if update_policy and isinstance(update_policy, dict):
            rec.update_policy = MemoryUpdatePolicy(
                promotion_rule=update_policy.get("promotion_rule"),
                decay_rule=update_policy.get("decay_rule"),
                consolidation_batch=update_policy.get("consolidation_batch"),
            )
        self.store.add(rec)
        
        # --- PHASE 4 HOOK START ---
        if self.graph_builder and (relations or rec.kind == "semantic" or rec.kind == "procedural"):
            try:
                # Some deployments use lightweight graph backends without full sync APIs.
                sync_node = getattr(self.graph_service, "sync_node", None)
                if callable(sync_node):
                    sync_node(NodeType.MEMORY, rec.id, title=rec.content[:200])  # type: ignore[misc]
                # Sync relations if builder API is available.
                if relations and hasattr(self.graph_builder, "sync_memory_relations"):
                    self.graph_builder.sync_memory_relations(rec.id, relations, rec.content[:200])
                
                # Proactive Extraction (Phase 4): Extract entities from content for MTS or Semantic records
                if self.graph_extractor and (rec.tier == MemoryTier.MTS or rec.kind == "semantic"):
                    # Trigger extraction in a non-blocking background task if possible, 
                    # but for core fabric we might want it synchronous for consistency.
                    # Given it uses LLM, we use a task to not block the main loop.
                    asyncio.create_task(self.graph_extractor.extract_and_store(rec.content))
            except Exception as e:
                logger.warning(f"Graph sync failed for memory {rec.id}: {e}")
        # --- PHASE 4 HOOK END ---

        logger.info("MemoryFabric: remembered %s tier=%s vector=%s", rec.id, rec.tier, vector_status)
        
        self._record_trace(
            "remember",
            {
                "id": rec.id,
                "tier": rec.tier.value,
                "source": rec.source,
                "kind": rec.kind,
                "importance": rec.importance,
                "vector_status": vector_status,
            },
        )
        return rec

    def remember_many_atomic(
        self,
        items: List[Dict[str, Any]],
        *,
        default_tier: MemoryTier = MemoryTier.STS,
    ) -> List[MemoryRecord]:
        """
        Batch memory write path with provider-aware embedding batching and fingerprint cache.
        """
        if not items:
            return []

        from quentin.infra.security.scrubber import CredentialScrubber

        scrubbed_items: List[Dict[str, Any]] = []
        embed_texts: List[str] = []
        embed_index: List[int] = []
        for i, raw in enumerate(items):
            content = CredentialScrubber.scrub_text(str(raw.get("content") or ""))
            metadata = CredentialScrubber.scrub_data(dict(raw.get("metadata") or {}))
            rec = dict(raw)
            rec["content"] = content
            rec["metadata"] = metadata
            scrubbed_items.append(rec)
            if rec.get("vector") is None:
                embed_texts.append(content)
                embed_index.append(i)

        vectors: List[List[float]] = []
        if embed_texts and self.embedding_client:
            try:
                vectors = self.embedding_batcher.embed_texts(embed_texts)
            except Exception as e:
                logger.warning("MemoryFabric: batch embedding failed, fallback disabled: %s", e)
                vectors = [[] for _ in embed_texts]

        for offset, item_idx in enumerate(embed_index):
            v = vectors[offset] if offset < len(vectors) else []
            if v:
                scrubbed_items[item_idx]["vector"] = v
                meta = dict(scrubbed_items[item_idx].get("metadata") or {})
                meta["vector_status"] = "generated_batch"
                scrubbed_items[item_idx]["metadata"] = meta

        records: List[MemoryRecord] = []
        for item in scrubbed_items:
            rec = self.remember_atomic(
                content=str(item.get("content") or ""),
                source=str(item.get("source") or "unknown"),
                tier=item.get("tier") or default_tier,
                domain=item.get("domain"),
                topic=item.get("topic"),
                importance=float(item.get("importance") or 0.0),
                tags=item.get("tags"),
                metadata=item.get("metadata"),
                vector=item.get("vector"),
                kind=str(item.get("kind") or "episodic"),
                relations=item.get("relations"),
                update_policy=item.get("update_policy"),
            )
            records.append(rec)

        self._record_trace(
            "remember_batch",
            {
                "count": len(records),
                "with_vector": sum(1 for r in records if r.vector),
            },
        )
        return records

    def _guess_pg_dsn(self) -> Optional[str]:
        env_dsn = os.getenv("PG_DSN")
        if env_dsn:
            return env_dsn
        host = os.getenv("PG_HOST")
        if not host:
            return None
        port = os.getenv("PG_PORT", "5432")
        user = os.getenv("PG_USER", "postgres")
        password = os.getenv("PG_PASSWORD", "")
        db = os.getenv("PG_DB", "postgres")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    def _build_fts_query(self, text: str) -> Optional[str]:
        """
        P5: Ported from OpenClaw's buildFtsQuery.
        Converts raw text to strict AND boolean query for FTS5.
        """
        import re
        tokens = re.findall(r'[A-Za-z0-9_]+', text)
        if not tokens: return None
        # Wrap each token in quotes and join with AND
        return " AND ".join(f'"{t}"' for t in tokens)

    def recall(self, query: MemoryQuery, *, pre_search_sync: bool = True) -> List[MemoryRecord]:
        start = time.perf_counter()
        self._maybe_warn_text_index_gap()
        if pre_search_sync:
            self._run_pre_search_sync_hook(query)
        
        # P5: Surgery One Hundred and Six - Strict AND Filtering (OpenClaw Parity)
        if query.text and (query.text_mode or "").lower() == "fts":
            strict_text = self._build_fts_query(query.text)
            if strict_text:
                query.text = strict_text
                logger.debug(f"MemoryFabric: Expanded FTS query to: {query.text}")

        # P5: Surgery Twenty-seven - On-Search Real-time Sync
        # If the session has pending dirty data, flush it to memory before searching.
        session_id = getattr(query, "session_id", None) or os.getenv("QUENTIN_SESSION_ID", "global")
        from quentin.infra.sessions.dirty_sync import dirty_sync
        
        # Heuristic: If we are in hybrid or text mode, recency matters more.
        if dirty_sync.should_sync(session_id):
            logger.info(f"MemoryFabric: Session {session_id} is dirty. Triggering immediate sync before search.")
            # In a blocking call for 'recall', we do a synchronous-like flush
            # We don't want to wait for the 5s debounce timer.
            dirty_sync._do_sync(session_id)

        # P2-B: Intent Routing
        mode = (query.mode or "auto").strip().lower()
        
        # If auto, use router if enabled
        if mode == "auto":
            from quentin.config.feature_flags import feature_flags
            if feature_flags.memory_intent_router_v1:
                from quentin.memory.query_intent import intent_router
                intent = intent_router.route(query.text or "")
                
                # Map intent to mode
                if intent == "keyword_exact":
                    mode = "text_only"
                elif intent == "semantic_explore":
                    mode = "vector_only"
                else:
                    mode = "hybrid" # Default mixed
            else:
                # Legacy auto logic
                enable_defaults = os.getenv("QUENTIN_MEMORY_RECALL_DEFAULTS_ENABLE", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
                defaults = self._get_recall_defaults() if enable_defaults else None
                if defaults is not None:
                    try:
                        d_mode = str(getattr(defaults, "mode", "") or "").strip().lower()
                    except Exception:
                        d_mode = ""
                    if d_mode in ("vector_only", "text_only", "hybrid"):
                        mode = d_mode
        
        if mode not in ("auto", "vector_only", "text_only", "hybrid"):
            mode = "auto"
        query = self._apply_online_active_window(query)

        if mode == "text_only":
            text_query = MemoryQuery(**{**query.__dict__, "vector": None, "mode": "text_only"})
            records, used_fts = self._run_text_query_with_fallback(text_query)
            records = self._apply_domain_policy(records, text_query)
            return self._finalize_recall(
                text_query,
                records,
                mode=mode,
                use_vector=False,
                latency_ms=(time.perf_counter() - start) * 1000,
                debug_payload={"text_mode_fts_used": bool(used_fts)} if bool(text_query.debug) else None,
            )

        if mode == "vector_only":
            if not query.vector and query.text and self.embedding_client:
                try:
                    vec = self.embedding_client.embed_text(query.text)
                    if vec:
                        query.vector = vec
                except Exception as e:
                    logger.warning(f"MemoryFabric: query embedding failed: {e}")
            records = self.store.search(query)
            records = self._apply_domain_policy(records, query)
            return self._finalize_recall(
                query,
                records,
                mode=mode,
                use_vector=bool(query.vector),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        if mode == "hybrid":
            query = self._apply_online_active_window(query)
            text_top_k = query.k_text or query.top_k
            vec_top_k = query.k_vec or query.top_k
            query_text = str(query.text or "").strip()

            # Structured/symbolic queries (e.g. [CODE:E00123], ISSUE-1234) are
            # vulnerable to keyword starvation in vector-seeded fast path.
            critical_tokens: List[str] = []
            if query_text:
                critical_tokens.extend([m.group(0) for m in re.finditer(r"\[[^\]]+\]", query_text)])
                critical_tokens.extend(
                    [m.group(0) for m in re.finditer(r"\b[A-Z]+[-_:]?\d{2,}\b", query_text)]
                )
                # stable de-dup while preserving order
                seen_tok: Set[str] = set()
                critical_tokens = [t for t in critical_tokens if not (t in seen_tok or seen_tok.add(t))]
            has_structured_signal = bool(critical_tokens)

            # 2. Vector Search (Semantic)
            query_vector = query.vector
            if not query_vector and query.text and self.embedding_client:
                try:
                    vec = self.embedding_client.embed_text(query.text)
                    if vec:
                        query_vector = vec
                        query.vector = vec
                except Exception as e:
                    logger.warning(f"MemoryFabric: query embedding failed: {e}")
                    query_vector = None

            vec_results_raw: List[MemoryRecord] = []
            hybrid_fast_path_used = False
            hybrid_fast_fallback_used = False
            if query_vector:
                try:
                    seed_top_k = int(os.getenv("QUENTIN_MEMORY_HYBRID_VECTOR_SEED_TOPK", "200"))
                except Exception:
                    seed_top_k = 200
                seed_top_k = max(int(vec_top_k), int(query.top_k), max(10, seed_top_k))
                vec_query = MemoryQuery(
                    **{
                        **query.__dict__,
                        "text": None,
                        "vector": query_vector,
                        "top_k": seed_top_k,
                        "mode": "vector_only",
                    }
                )
                vec_results_raw = self.store.search(vec_query)

            # 1. Text Search (optimized path first)
            text_results_raw: List[MemoryRecord] = []
            fast_enabled = os.getenv("QUENTIN_MEMORY_HYBRID_FAST_VECTOR_SEED", "1").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if fast_enabled and vec_results_raw and query_text:
                hybrid_fast_path_used = True
                scored = []
                for i, r in enumerate(vec_results_raw):
                    s = self._score_text(query_text, r.content)
                    if s > 0.0:
                        scored.append((s, i, r))
                scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
                text_results_raw = [r for _, _, r in scored[: int(text_top_k)]]

                fallback_enabled = os.getenv("QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_ENABLE", "1").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
                try:
                    fallback_min_hits = int(os.getenv("QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_MIN_HITS", "1"))
                except Exception:
                    fallback_min_hits = 1
                has_critical_token_hit = True
                if has_structured_signal and text_results_raw:
                    has_critical_token_hit = any(
                        any(tok in str(r.content or "") for tok in critical_tokens) for r in text_results_raw
                    )
                need_fallback = len(text_results_raw) < max(0, fallback_min_hits)
                if has_structured_signal and not has_critical_token_hit:
                    need_fallback = True
                if fallback_enabled and need_fallback:
                    hybrid_fast_fallback_used = True
                    text_query = MemoryQuery(
                        **{**query.__dict__, "vector": None, "top_k": text_top_k, "mode": "text_only"}
                    )
                    text_results_raw, _ = self._run_text_query_with_fallback(text_query)
            else:
                text_query = MemoryQuery(**{**query.__dict__, "vector": None, "top_k": text_top_k, "mode": "text_only"})
                text_results_raw, _ = self._run_text_query_with_fallback(text_query)

            # 3. Microscope-level RRF Fusion (Surgery Twenty-six)
            from quentin.memory.hybrid_fusion import rrf_merge, SearchResult
            
            # P5: OpenClaw Parity - Weight Adjustment
            vector_weight = 0.6
            keyword_weight = 0.4
            
            if getattr(query, "domain", "") == "code":
                keyword_weight = 0.7 # In code, keywords (variable names) matter more
                vector_weight = 0.3
            elif getattr(query, "domain", "") == "chat":
                vector_weight = 0.8 # In chat, semantics matter more
                keyword_weight = 0.2
            elif has_structured_signal:
                # Structured query tokens should preserve lexical exactness.
                keyword_weight = 0.55
                vector_weight = 0.45

            # Convert to SearchResult for fusion
            v_items = [
                SearchResult(id=r.id, path=r.metadata.get("path", ""), content=r.content, metadata=r.metadata)
                for r in vec_results_raw
            ]
            k_items = [
                SearchResult(id=r.id, path=r.metadata.get("path", ""), content=r.content, metadata=r.metadata)
                for r in text_results_raw
            ]

            fused_results = rrf_merge(
                vector_results=v_items,
                keyword_results=k_items,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
                k=60 # Standard OpenClaw constant
            )

            # 4. Map back to MemoryRecords and finalize
            records = []
            record_map = {r.id: r for r in (vec_results_raw + text_results_raw)}
            for f in fused_results[: query.top_k]:
                rec = record_map[f.id]
                rec.importance = f.score # Assign fused score
                records.append(rec)

            # Keep top keyword anchors so exact text hits are not starved by vector-dominant fusion.
            try:
                anchor_n = int(os.getenv("QUENTIN_MEMORY_HYBRID_KEYWORD_ANCHOR_TOPN", "2"))
            except Exception:
                anchor_n = 2
            if has_structured_signal:
                anchor_n = max(anchor_n, min(2, int(query.top_k)))
            anchor_n = max(0, anchor_n)
            if anchor_n > 0 and text_results_raw:
                anchors = text_results_raw[:anchor_n]
                anchor_ids = {a.id for a in anchors}
                merged: List[MemoryRecord] = []
                for anchor in anchors:
                    anchor.importance = max(float(getattr(anchor, "importance", 0.0) or 0.0), 0.95)
                    merged.append(anchor)
                if merged:
                    merged.extend([r for r in records if r.id not in anchor_ids])
                    records = merged[: query.top_k]

            # P5: Surgery Fifty-three - KG Hedging (OpenClaw Parity)
            # If the top result is weak, we jump to connected entities to find logical neighbors.
            if records and records[0].importance < 0.7:
                logger.info("MemoryFabric: Weak vector scores. Triggering Graph-Hop Hedging.")
                expansion = self._graph_hop_expand([r.id for r in records[:3]], limit=5)
                existing_ids = {r.id for r in records}
                for exp_rec in expansion:
                    if exp_rec.id not in existing_ids:
                        exp_rec.importance = 0.65 # Secondary boost for logical relevance
                        records.append(exp_rec)
                        existing_ids.add(exp_rec.id)

            records = self._apply_domain_policy(records, query)

            debug = bool(query.debug or os.getenv("QUENTIN_MEMORY_DEBUG", "").strip() in ("1", "true", "yes"))
            debug_payload = None
            if debug:
                debug_payload = {
                    "mode": "hybrid_rrf_v2",
                    "text_count": len(text_results_raw),
                    "vec_count": len(vec_results_raw),
                    "fused_count": len(fused_results),
                    "hybrid_fast_path_used": bool(hybrid_fast_path_used),
                    "hybrid_fast_fallback_used": bool(hybrid_fast_fallback_used),
                    "hybrid_seed_candidates": len(vec_results_raw),
                    "hybrid_text_seed_hits": len(text_results_raw),
                    "weights": {"text": keyword_weight, "vec": vector_weight},
                    "top_scores": {f.id: f.score for f in fused_results[:5]}
                }
            return self._finalize_recall(
                query,
                records,
                mode=mode,
                use_vector=bool(query_vector),
                latency_ms=(time.perf_counter() - start) * 1000,
                debug_payload=debug_payload,
            )

        if not query.vector and query.text and self.embedding_client:
            try:
                vec = self.embedding_client.embed_text(query.text)
                if vec:
                    query.vector = vec
            except Exception as e:
                logger.warning(f"MemoryFabric: query embedding failed: {e}")

        records = self.store.search(query)
        records = self._apply_domain_policy(records, query)
        
        return self._finalize_recall(
            query,
            records,
            mode=mode,
            use_vector=bool(query.vector),
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _apply_domain_policy(self, records: List[MemoryRecord], query: MemoryQuery) -> List[MemoryRecord]:
        # Cross-domain recall policy (blueprint v3):
        # - If query.domain is set, allow matching domain plus `domain="cross"` when include_cross_domain=True.
        if not getattr(query, "domain", None):
            return records
        want = str(getattr(query, "domain", "") or "").strip().lower()
        include_cross = bool(getattr(query, "include_cross_domain", True))

        def _match(rec: MemoryRecord) -> bool:
            dom = (getattr(rec, "domain", None) or "").strip().lower()
            if not dom:
                # Treat missing domain as core for backward compatibility.
                dom = "core"
            if dom == want:
                return True
            if include_cross and dom == "cross":
                return True
            return False

        return [r for r in records if _match(r)]

    def run_garbage_collection(self) -> Dict[str, Any]:
        """
        P5: Ported from OpenClaw's memory cleanup jobs.
        Scans, decays, and expires old/irrelevant memories.
        """
        from quentin.memory.decay_engine import MemoryDecayEngine
        engine = MemoryDecayEngine()
        
        # 1. Fetch all non-decayed records (STS and MTS)
        # Note: In a real system, we'd use a more efficient SQL batch update
        records = self.store.get_candidates_for_consolidation(tier=MemoryTier.STS, limit=5000)
        records += self.store.get_candidates_for_consolidation(tier=MemoryTier.MTS, limit=5000)
        
        decayed_count = 0
        expired_count = 0
        
        for rec in records:
            # A. Update Importance (Time-based Decay)
            new_importance = engine.calculate_decay(rec.importance, rec.updated_at)
            
            # B. Check for physical expiration
            if engine.should_expire(new_importance, rec.last_accessed_at):
                self.decay_records([rec.id]) # Mark as decayed in DB
                expired_count += 1
            elif abs(new_importance - rec.importance) > 0.01:
                rec.importance = new_importance
                self.store.update(rec)
                decayed_count += 1
                
        logger.info(f"MemoryFabric: GC Finished. {decayed_count} decayed, {expired_count} expired.")
        return {"decayed": decayed_count, "expired": expired_count}

    def _graph_hop_expand(self, seed_ids: List[str], limit: int = 5) -> List[MemoryRecord]:
        """
        P5: Ported from OpenClaw's graph-hop logic.
        Finds records that share entities with the seed records.
        """
        if not hasattr(self.store, "conn") or not seed_ids:
            return []
            
        # Note: knowledge-graph tables exist in sqlite store; Postgres store may not have them yet.
        # Keep this best-effort and avoid breaking recall if unsupported.
        sql = """
            SELECT DISTINCT m.*
            FROM memories m
            JOIN memory_entity_map mem1 ON m.id = mem1.memory_id
            JOIN memory_entity_map mem2 ON mem1.entity_name = mem2.entity_name
            WHERE mem2.memory_id IN ({})
              AND m.id NOT IN ({})
              AND m.decayed = {}
            LIMIT {}
        """.format(
            ",".join(["?"] * len(seed_ids)),
            ",".join(["?"] * len(seed_ids)),
            "0",
            "?"
        )
        # Postgres boolean compatibility: if sqlite-style fails, retry with FALSE and %s placeholders.
        
        try:
            params = seed_ids + seed_ids + [limit]
            cur = self.store.conn.execute(sql, params)
            rows = cur.fetchall()
            return [self.store._row_to_record(r) for r in rows]
        except Exception as e:
            try:
                sql_pg = """
                    SELECT DISTINCT m.*
                    FROM memories m
                    JOIN memory_entity_map mem1 ON m.id = mem1.memory_id
                    JOIN memory_entity_map mem2 ON mem1.entity_name = mem2.entity_name
                    WHERE mem2.memory_id = ANY(%(seed)s)
                      AND NOT (m.id = ANY(%(seed)s))
                      AND m.decayed = FALSE
                    LIMIT %(limit)s
                """
                cur = self.store.conn.execute(sql_pg, {"seed": seed_ids, "limit": int(limit)})
                rows = cur.fetchall()
                return [self.store._row_to_record(r) for r in rows]
            except Exception:
                logger.warning(f"MemoryFabric: Graph expansion failed: {e}")
            return []

    def promote_to_mts(self, record_ids: List[str]) -> None:
        for rid in record_ids:
            self.store.promote(rid, MemoryTier.MTS)
        logger.info("MemoryFabric: promoted %d records to MTS", len(record_ids))
        self._record_trace("promote_to_mts", {"ids": record_ids})

    def promote_to_lts(self, record_ids: List[str]) -> None:
        for rid in record_ids:
            self.store.promote(rid, MemoryTier.LTS)
        logger.info("MemoryFabric: promoted %d records to LTS", len(record_ids))
        self._record_trace("promote_to_lts", {"ids": record_ids})

    def decay_records(self, record_ids: List[str]) -> None:
        for rid in record_ids:
            self.store.mark_decayed(rid)
        logger.info("MemoryFabric: marked %d records decayed", len(record_ids))
        self._record_trace("decay_records", {"ids": record_ids})

    def sync_file_delta(
        self,
        file_path: str | Path,
        tier: MemoryTier = MemoryTier.STS,
        importance: float = 0.4
    ) -> Optional[MemoryRecord]:
        """
        P5: Ported from OpenClaw's 'syncLogFile'.
        Incrementally reads and indexes ONLY the new content of a file.
        """
        from quentin.utils.io_utils import IOUtils
        path_str = str(file_path)
        
        # 1. Retrieve last known offset from DB (using metadata or specialized table)
        # For simplicity in this surgery, we check our existing memory records for this file
        last_offset = 0
        existing = self.store.search(MemoryQuery(text=path_str, top_k=1, mode="text_only"))
        if existing:
            last_offset = existing[0].metadata.get("last_read_offset", 0)
            
        # 2. Read only the new bytes
        new_content, new_offset = IOUtils.read_delta(path_str, last_offset)
        
        if not new_content.strip():
            return None
            
        # 3. Remember the delta with offset metadata
        rec = self.remember_atomic(
            content=f"LOG DELTA [{path_str}]:\n{new_content}",
            source=f"file:delta:{path_str}",
            tier=tier,
            importance=importance,
            tags=["file_delta", "log"],
            metadata={
                "file_path": path_str,
                "last_read_offset": new_offset,
                "delta_size": len(new_content)
            }
        )
        
        logger.info(f"MemoryFabric: Synced {len(new_content)} new bytes from {path_str}.")
        return rec

    def sync_session_file_delta(
        self,
        file_path: str | Path,
        *,
        last_offset: Optional[int] = None,
        tier: MemoryTier = MemoryTier.STS,
        importance: float = 0.35,
    ) -> Dict[str, Any]:
        """
        OpenClaw parity increment:
        Incrementally parse session transcript JSONL and index only new user/assistant lines.
        """
        abs_path = str(Path(file_path).resolve())
        start_offset = int(last_offset) if last_offset is not None else int(self._session_file_offsets.get(abs_path, 0))
        delta = build_session_delta(abs_path, last_offset=start_offset)
        session_path = session_path_for_file(abs_path)
        if delta is None:
            return {"status": "noop", "path": session_path, "offset": start_offset}

        self._session_file_offsets[abs_path] = int(delta.next_offset)
        base = {
            "path": delta.path,
            "offset": int(delta.next_offset),
            "read_bytes": int(delta.read_bytes),
            "message_count": int(delta.message_count),
            "hash": delta.hash,
        }
        if not delta.content:
            return {"status": "advanced", **base}

        rec = self.remember_atomic(
            content=delta.content,
            source=f"session_file:{delta.path}",
            tier=tier,
            importance=importance,
            tags=["session_file", "session_delta"],
            metadata={
                "session_file": True,
                "file_path": abs_path,
                "session_path": delta.path,
                "start_offset": int(delta.start_offset),
                "last_read_offset": int(delta.next_offset),
                "delta_size": int(delta.read_bytes),
                "message_count": int(delta.message_count),
                "hash": delta.hash,
            },
        )
        return {"status": "indexed", "record_id": rec.id, **base}

    def remember_file(
        self,
        file_path: str | Path,
        tier: MemoryTier = MemoryTier.MTS,
        importance: float = 0.5,
        tags: Optional[list] = None,
        source_prefix: str = "file",
    ) -> List[MemoryRecord]:
        """
        P5: Ported from OpenClaw's 'indexFile'.
        Reads a file, chunks it with Title Injection, and stores segments.
        """
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"MemoryFabric: {file_path} not found.")
            
        content = p.read_text(encoding="utf-8", errors="ignore")
        function_fingerprints = build_code_function_fingerprints(file_path=str(file_path), content=content)
        function_fingerprint_hash = build_function_fingerprint_hash(
            function_fingerprints,
            position_insensitive=True,
        )
        prev_hash = self._get_cached_file_function_hash(str(p.resolve()))
        if function_fingerprint_hash and prev_hash == function_fingerprint_hash:
            logger.info("MemoryFabric: skip reindex for %s (function fingerprint unchanged)", file_path)
            return []

        source_value = f"{source_prefix}:{str(p.resolve())}"
        conn = getattr(self.store, "conn", None)
        if conn is not None:
            try:
                conn.execute("DELETE FROM memories WHERE source = ?", (source_value,))
                conn.commit()
            except Exception:
                pass
        
        # 1. Chunking with Semantic Augmentation (Surgery Twenty-eight)
        from quentin.memory.processors.markdown_splitter import MarkdownSplitter
        splitter = MarkdownSplitter()
        chunks = splitter.split(content, file_path=str(file_path))
        
        records = []
        for chunk in chunks:
            # 2. Store each chunk atomically
            rec = self.remember_atomic(
                content=chunk.text,
                source=source_value,
                tier=tier,
                importance=importance,
                tags=(tags or []) + ["file_chunk"],
                metadata={
                    **chunk.metadata,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "function_fingerprints": function_fingerprints,
                    "function_fingerprint_hash": function_fingerprint_hash,
                }
            )
            records.append(rec)
        if function_fingerprint_hash:
            self._set_cached_file_function_hash(str(p.resolve()), function_fingerprint_hash)
        logger.info(f"MemoryFabric: Indexed {file_path} into {len(records)} semantic chunks.")
        return records

    def sync_memory_files(
        self,
        *,
        workspace_dir: Optional[str | Path] = None,
        force: bool = False,
        dirty_files: Optional[Set[str]] = None,
        concurrency: int = 0,
        progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        tier: MemoryTier = MemoryTier.MTS,
        importance: float = 0.5,
        tags: Optional[list] = None,
        source_prefix: str = "memory_file",
    ) -> Dict[str, Any]:
        files = self._list_memory_markdown_files(workspace_dir=workspace_dir)
        active_paths = {str(p) for p in files}
        dirty_abs = {str(Path(x).resolve()) for x in (dirty_files or set())}
        index_all = force or not dirty_abs

        total = len(files)
        completed = 0
        indexed = 0
        skipped = 0
        errors = 0

        def _report(label: Optional[str] = None) -> None:
            if progress is None:
                return
            payload = {"completed": completed, "total": total}
            if label:
                payload["label"] = label
            progress(payload)

        _report(label="Indexing memory files...")

        def _task(path: Path) -> str:
            abs_path = str(path.resolve())
            if (not index_all) and abs_path not in dirty_abs:
                return "skipped"
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return "error"
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            prev = self._get_memory_file_content_hash(abs_path)
            if (not force) and prev and prev == content_hash:
                return "skipped"
            with self._memory_sync_write_lock:
                recs = self.remember_file(
                    path,
                    tier=tier,
                    importance=importance,
                    tags=tags,
                    source_prefix=source_prefix,
                )
            if recs:
                self._set_memory_file_content_hash(abs_path, content_hash)
                return "indexed"
            # Function fingerprint unchanged may skip remember_file. Hash still updates.
            self._set_memory_file_content_hash(abs_path, content_hash)
            return "skipped"

        effective_concurrency = int(concurrency or self.runtime_config.sync_concurrency or 1)
        with ThreadPoolExecutor(max_workers=max(1, min(int(effective_concurrency), max(1, total)))) as pool:
            futures = [pool.submit(_task, p) for p in files]
            for fut in as_completed(futures):
                try:
                    status = fut.result()
                except Exception:
                    status = "error"
                completed += 1
                if status == "indexed":
                    indexed += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1
                _report()

        deleted = self._cleanup_stale_memory_file_records(active_paths=active_paths, source_prefix=source_prefix)
        return {
            "total": total,
            "completed": completed,
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
            "stale_deleted": deleted,
            "index_all": index_all,
        }

    def recall_across_sessions(
        self,
        *,
        query: MemoryQuery,
        session_sources: Dict[str, List[str]],
        session_options: Optional[Dict[str, Dict[str, Any]]] = None,
        top_k: Optional[int] = None,
        per_session_factor: int = 3,
        rrf_k: int = 60,
    ) -> Dict[str, Any]:
        """
        Cross-session parallel recall scheduler (OpenClaw search-manager parity increment).

        `session_sources` maps session id -> source prefixes,
        e.g. {"s1": ["session_delta:s1", "session_file:sessions/s1"]}.
        """
        self._run_pre_search_sync_hook(query)
        specs: List[SessionSearchSpec] = []
        for sid, prefixes in (session_sources or {}).items():
            if not sid:
                continue
            ps = [str(p or "") for p in (prefixes or []) if str(p or "")]
            opts = (session_options or {}).get(str(sid), {})
            try:
                w = float(opts.get("weight", 1.0))
            except Exception:
                w = 1.0
            try:
                pr = int(opts.get("priority", 0))
            except Exception:
                pr = 0
            tk = opts.get("top_k_override")
            try:
                tk_int = int(tk) if tk is not None else None
            except Exception:
                tk_int = None
            specs.append(
                SessionSearchSpec(
                    session_id=str(sid),
                    source_prefixes=ps,
                    weight=w,
                    priority=pr,
                    top_k_override=tk_int,
                )
            )
        result = self._parallel_search_manager.search_across_sessions(
            memory_fabric=self,
            base_query=query,
            session_specs=specs,
            top_k=top_k,
            per_session_factor=per_session_factor,
            rrf_k=rrf_k,
        )
        self._record_trace(
            "recall_across_sessions",
            {
                "query_text": query.text,
                "top_k": int(top_k if top_k is not None else query.top_k),
                "total_sessions": int(result.get("total_sessions") or 0),
                "result_count": len(result.get("records") or []),
                "session_hits": result.get("session_hits") or {},
                "scheduled_sessions": result.get("scheduled_sessions") or [],
                "rerank_applied": bool(result.get("rerank_applied")),
                "errors": result.get("errors") or {},
                "timed_out_sessions": result.get("timed_out_sessions") or [],
            },
        )
        return result

    async def recall_across_sessions_async(
        self,
        *,
        query: MemoryQuery,
        session_sources: Dict[str, List[str]],
        session_options: Optional[Dict[str, Dict[str, Any]]] = None,
        top_k: Optional[int] = None,
        per_session_factor: int = 3,
        rrf_k: int = 60,
        cancel_event: Optional[asyncio.Event] = None,
        overall_timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        self._run_pre_search_sync_hook(query)
        specs: List[SessionSearchSpec] = []
        for sid, prefixes in (session_sources or {}).items():
            if not sid:
                continue
            ps = [str(p or "") for p in (prefixes or []) if str(p or "")]
            opts = (session_options or {}).get(str(sid), {})
            try:
                w = float(opts.get("weight", 1.0))
            except Exception:
                w = 1.0
            try:
                pr = int(opts.get("priority", 0))
            except Exception:
                pr = 0
            tk = opts.get("top_k_override")
            try:
                tk_int = int(tk) if tk is not None else None
            except Exception:
                tk_int = None
            specs.append(
                SessionSearchSpec(
                    session_id=str(sid),
                    source_prefixes=ps,
                    weight=w,
                    priority=pr,
                    top_k_override=tk_int,
                )
            )

        if overall_timeout_s is None:
            try:
                overall_timeout_s = float(self.runtime_config.search_overall_timeout_s) or None
            except Exception:
                overall_timeout_s = None

        result = await self._parallel_search_manager.search_across_sessions_async(
            memory_fabric=self,
            base_query=query,
            session_specs=specs,
            top_k=top_k,
            per_session_factor=per_session_factor,
            rrf_k=rrf_k,
            cancel_event=cancel_event,
            overall_timeout_s=overall_timeout_s,
        )
        self._record_trace(
            "recall_across_sessions_async",
            {
                "query_text": query.text,
                "top_k": int(top_k if top_k is not None else query.top_k),
                "total_sessions": int(result.get("total_sessions") or 0),
                "result_count": len(result.get("records") or []),
                "session_hits": result.get("session_hits") or {},
                "scheduled_sessions": result.get("scheduled_sessions") or [],
                "rerank_applied": bool(result.get("rerank_applied")),
                "errors": result.get("errors") or {},
                "timed_out_sessions": result.get("timed_out_sessions") or [],
                "cancelled_sessions": result.get("cancelled_sessions") or [],
                "cancelled": bool(result.get("cancelled")),
            },
        )
        return result

    # ---- consolidation helpers for SleepLoop ----

    def get_sts_for_consolidation(self, limit: int = 200) -> List[MemoryRecord]:
        return self.store.get_candidates_for_consolidation(
            tier=MemoryTier.STS,
            limit=limit,
        )

    def get_records_for_processing(self, tier: MemoryTier, limit: int = 200) -> List[MemoryRecord]:
        """
        Generic method to retrieve records from a specific tier for processing (consolidation, promotion, decay).
        """
        return self.store.get_candidates_for_consolidation(
            tier=tier,
            limit=limit,
        )

    def run_safe_forgetting(self, *, config: Optional[Any] = None) -> Dict[str, Any]:
        """
        Safe forgetting job (blueprint v3):
        - STS cleanup
        - MTS dedup/compaction (v1 exact match)
        - LTS replacement semantics are represented via supersedes fields (no deletion)
        """
        from quentin.memory.forgetting import run_safe_forgetting

        return run_safe_forgetting(fabric=self, config=config)

    def write_consolidated_summary(
        self,
        summary_content: str,
        source: str,
        from_records: List[MemoryRecord],
        target_tier: MemoryTier = MemoryTier.MTS,
        importance: float = 0.8,
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
        topic: Optional[str] = None,
    ) -> MemoryRecord:
        # Recursive call to remember_atomic so consolidated memories also get embeddings!
        return self.remember_atomic(
            content=summary_content,
            source=source,
            tier=target_tier,
            importance=importance,
            tags=tags,
            metadata={**(metadata or {}), "consolidated": True},
            kind="semantic", # Summaries are semantic
            topic=topic,
        )

    def reindex_indexes(self) -> Dict[str, Any]:
        if not hasattr(self.store, "reindex_indexes"):
            return {"status": "unsupported"}
        start = time.perf_counter()
        try:
            result = self.store.reindex_indexes()  # type: ignore[attr-defined]
        except Exception as e:
            result = {"status": "failed", "error": str(e)}
        result["duration_ms"] = int((time.perf_counter() - start) * 1000)
        try:
            self._record_trace("reindex", {"result": result})
        except Exception:
            pass
        return result

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "store": type(self.store).__name__,
            "provider": "unknown",
            "model": "unknown",
            "batch": {},
            "search": {},
            "vector": {
                "enabled": False,
                "ready": None,
                "backend": "unknown",
                "math_backend": "unknown",
                "fetch_strategy": "unknown",
            },
            "tier_counts": {
                "short_term": 0,
                "mid_term": 0,
                "long_term": 0,
            },
            "total_records": 0,
        }

        try:
            cfg = getattr(self.embedding_client, "_cfg", None)
            if cfg is not None:
                out["provider"] = str(getattr(cfg, "provider", out["provider"]) or out["provider"])
                out["model"] = str(getattr(cfg, "model", out["model"]) or out["model"])
            else:
                out["provider"] = str(getattr(self.embedding_client, "provider", out["provider"]) or out["provider"])
                out["model"] = str(getattr(self.embedding_client, "model_name", out["model"]) or out["model"])
        except Exception:
            pass

        try:
            out["batch"] = self.embedding_batcher.status()
        except Exception:
            out["batch"] = {"available": False}
        try:
            cfg = getattr(self._parallel_search_manager, "config", None)
            out["search"] = {
                "available": True,
                "max_workers": int(getattr(cfg, "max_workers", 0) or 0),
                "per_session_timeout_s": float(getattr(cfg, "per_session_timeout_s", 0.0) or 0.0),
                "rerank_enabled": bool(getattr(cfg, "rerank_enabled", False)),
                "rerank_half_life_hours": float(getattr(cfg, "rerank_time_half_life_hours", 0.0) or 0.0),
                "runtime_profile": str(getattr(self.runtime_config, "profile", "unknown") or "unknown"),
                "sync_concurrency": int(getattr(self.runtime_config, "sync_concurrency", 0) or 0),
                "online_active_window_enabled": os.getenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_ENABLE", "1")
                .strip()
                .lower()
                in ("1", "true", "yes", "on"),
                "online_offline_threshold": int(
                    str(os.getenv("QUENTIN_MEMORY_ONLINE_OFFLINE_THRESHOLD", "300000") or "300000")
                ),
                "online_active_window_days": int(
                    str(os.getenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_DAYS", "90") or "90")
                ),
            }
        except Exception:
            out["search"] = {"available": False}

        try:
            vec_ready = bool(getattr(self.store, "_vec_ready", False))
            vec_backend = str(getattr(self.store, "_vector_backend", "") or "").strip().lower() or (
                "sqlite_vec" if vec_ready else "client_scan"
            )
            out["vector"] = {
                "enabled": bool(vec_ready or hasattr(self.store, "_vector_search_vec0") or hasattr(self.store, "_vector_search")),
                "ready": vec_ready,
                "backend": vec_backend,
                "math_backend": str(getattr(self.store, "_vector_math_backend", "unknown")),
                "fetch_strategy": str(getattr(self.store, "_vector_fetch_strategy", "unknown")),
            }
        except Exception:
            pass

        try:
            if hasattr(self.store, "conn"):
                cur = self.store.conn.execute(
                    """
                    SELECT tier, COUNT(*) AS c
                    FROM memories
                    WHERE decayed = 0
                    GROUP BY tier
                    """
                )
                mapping = {
                    MemoryTier.STS.value: "short_term",
                    MemoryTier.MTS.value: "mid_term",
                    MemoryTier.LTS.value: "long_term",
                }
                total = 0
                for row in cur.fetchall():
                    tier = str(row["tier"])
                    count = int(row["c"] or 0)
                    total += count
                    key = mapping.get(tier)
                    if key:
                        out["tier_counts"][key] = count
                out["total_records"] = total
        except Exception:
            pass

        warnings: List[str] = []
        try:
            total = int(out.get("total_records") or 0)
            has_fts = bool(getattr(self.store, "_fts_enabled", False))
            vec_ready = bool(getattr(self.store, "_vec_ready", False))
            if total >= 50000 and (not has_fts) and (not vec_ready):
                warnings.append("large_corpus_without_fts_or_sqlite_vec")
        except Exception:
            pass
        if warnings:
            out["warnings"] = warnings

        return out


    def export_to_markdown(self, output_dir: str | Path = "data/memory_markdown") -> Dict[str, Any]:
        """
        Phase 5.3: Export all active memory records to human-readable Markdown files.
        Mirroring OpenClaw's transparency.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        tiers = [MemoryTier.STS, MemoryTier.MTS, MemoryTier.LTS]
        exported_count = 0
        
        for tier in tiers:
            recs = self.store.get_candidates_for_consolidation(tier=tier, limit=10000)
            if not recs: continue
            
            content = [f"# Memory Export: {tier.value}\n", f"Generated: {now_utc().isoformat()}\n"]
            
            for r in recs:
                content.append(f"## Record {r.id}")
                content.append(f"- **Source**: {r.source}")
                content.append(f"- **Kind**: {r.kind}")
                content.append(f"- **Importance**: {r.importance}")
                content.append(f"- **Tags**: {', '.join(r.tags)}")
                content.append(f"- **Created**: {r.created_at.isoformat()}")
                content.append("\n### Content\n")
                content.append(r.content)
                content.append("\n---\n")
                exported_count += 1
            
            tier_file = out_path / f"{tier.value}.md"
            print(f"DEBUG: Exporting to {tier_file.resolve()}")
            tier_file.write_text("\n".join(content), encoding="utf-8")
            
        return {"status": "ok", "exported_records": exported_count, "output_dir": str(out_path)}

FileBackedMemoryFabric = MemoryFabric
