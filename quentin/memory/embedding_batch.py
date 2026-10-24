from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypeVar

import httpx

from quentin.infra.llm.embeddings import EmbeddingClient
from quentin.utils.time import now_utc
from quentin.memory.openai_batch_protocol import (
    create_batch_job,
    fetch_output_lines,
    upload_batch_file,
    wait_batch_output_file,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class RetryableBatchError(RuntimeError):
    pass


class NonRetryableBatchError(RuntimeError):
    pass


class ProviderDisabledBatchError(RuntimeError):
    pass


def _stable_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def build_embedding_fingerprint(*, provider: str, model: str, text: str) -> str:
    payload = f"{provider}|{model}|{_stable_text(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_header_names(headers: Optional[Dict[str, str]]) -> List[str]:
    if not headers:
        return []
    out: List[str] = []
    for k in headers.keys():
        key = str(k or "").strip().lower()
        if key:
            out.append(key)
    out.sort()
    return out


def build_batch_fingerprint(*, provider: str, model: str, texts: Sequence[str]) -> str:
    base = [build_embedding_fingerprint(provider=provider, model=model, text=t) for t in texts]
    return hashlib.sha256("|".join(base).encode("utf-8")).hexdigest()


def resolve_batch_concurrency(*, account_tier: int, configured: int) -> int:
    """
    OpenClaw-style dynamic flow control.
    - Tier 1: conservative concurrency
    - Tier 5: high concurrency for large-scale batching
    """
    tier = max(1, min(5, int(account_tier or 1)))
    floor_by_tier = {1: 2, 2: 4, 3: 8, 4: 16, 5: 100}
    floor = floor_by_tier.get(tier, 2)
    if configured <= 0:
        return floor
    return max(1, min(100, max(floor, int(configured))))


class EmbeddingCache:
    """
    Persistent cache to physically block repeated embedding calls.
    """

    def __init__(self, cache_path: str | Path) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.cache_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                fingerprint TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_hit_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def get(self, fingerprint: str) -> Optional[List[float]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT vector_json, hit_count FROM embedding_cache WHERE fingerprint = ?",
                (fingerprint,),
            )
            row = cur.fetchone()
            if not row:
                return None
            now = now_utc().isoformat()
            self._conn.execute(
                "UPDATE embedding_cache SET hit_count = ?, last_hit_at = ? WHERE fingerprint = ?",
                (int(row["hit_count"]) + 1, now, fingerprint),
            )
            self._conn.commit()
            try:
                return json.loads(row["vector_json"])
            except Exception:
                return None

    def put(self, *, fingerprint: str, provider: str, model: str, vector: List[float]) -> None:
        now = now_utc().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO embedding_cache (
                    fingerprint, provider, model, dim, vector_json, created_at, last_hit_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT hit_count FROM embedding_cache WHERE fingerprint = ?), 0))
                """,
                (
                    fingerprint,
                    provider,
                    model,
                    len(vector),
                    json.dumps(vector),
                    now,
                    now,
                    fingerprint,
                ),
            )
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS c FROM embedding_cache")
            row = cur.fetchone()
            if not row:
                return 0
            return int(row["c"] or 0)


class BatchJobStore:
    """
    Persistent async batch job state for crash-safe resume.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_batch_jobs (
                fingerprint TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                status TEXT NOT NULL,
                output_file_id TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, fingerprint: str) -> Optional[Dict[str, str]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT fingerprint, provider, model, batch_id, status, output_file_id, error, updated_at
                FROM embedding_batch_jobs
                WHERE fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()
            if not row:
                return None
            return {
                "fingerprint": str(row["fingerprint"] or ""),
                "provider": str(row["provider"] or ""),
                "model": str(row["model"] or ""),
                "batch_id": str(row["batch_id"] or ""),
                "status": str(row["status"] or ""),
                "output_file_id": str(row["output_file_id"] or ""),
                "error": str(row["error"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }

    def upsert(
        self,
        *,
        fingerprint: str,
        provider: str,
        model: str,
        batch_id: str,
        status: str,
        output_file_id: str = "",
        error: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO embedding_batch_jobs (
                    fingerprint, provider, model, batch_id, status, output_file_id, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    provider,
                    model,
                    batch_id,
                    status,
                    output_file_id,
                    error,
                    now_utc().isoformat(),
                ),
            )
            self._conn.commit()


@dataclass
class BatchEmbeddingConfig:
    provider: str = "disabled"
    model: str = "unknown"
    provider_key: str = "unknown"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    timeout_s: float = 20.0
    batch_size: int = 128
    batch_failure_limit: int = 2
    openai_async_batch_enabled: bool = False
    openai_async_batch_wait: bool = True
    openai_async_poll_interval_s: float = 2.0
    openai_async_timeout_s: float = 120.0
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: str = ""
    gemini_async_batch_enabled: bool = False
    gemini_async_batch_wait: bool = True
    gemini_async_poll_interval_s: float = 2.0
    gemini_async_timeout_s: float = 120.0
    account_tier: int = 1
    batch_concurrency: int = 2
    retry_max_attempts: int = 3
    retry_base_delay_ms: int = 300
    retry_max_delay_ms: int = 2000
    job_store_path: str = ""


class BatchEmbeddingManager:
    """
    Provider-aware batch embedding with differential fingerprint cache.
    """

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        config: BatchEmbeddingConfig,
        cache: Optional[EmbeddingCache] = None,
    ) -> None:
        self.embedding_client = embedding_client
        self.config = config
        self.cache = cache
        self.job_store = BatchJobStore(self.config.job_store_path) if str(self.config.job_store_path or "").strip() else None
        self._batch_failures = 0
        self._batch_enabled = True
        self._batch_concurrency = resolve_batch_concurrency(
            account_tier=self.config.account_tier,
            configured=self.config.batch_concurrency,
        )
        self._retry_attempts_total = 0
        self._fallback_calls_total = 0
        self._resumed_jobs_total = 0
        self._provider_disabled_total = 0

    def embed_text(self, text: str) -> List[float]:
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else []

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []

        provider = (self.config.provider or "unknown").strip().lower()
        model = self.config.model or "unknown"
        provider_key = self.config.provider_key or "unknown"
        out: List[Optional[List[float]]] = [None] * len(texts)
        misses: Dict[str, List[int]] = {}

        for i, text in enumerate(texts):
            fp = build_embedding_fingerprint(
                provider=provider,
                model=f"{model}::{provider_key}",
                text=text,
            )
            cached = self.cache.get(fp) if self.cache else None
            if cached:
                out[i] = cached
                continue
            misses.setdefault(fp, []).append(i)

        if misses:
            unique_texts: List[str] = []
            unique_fps: List[str] = []
            for fp, idxs in misses.items():
                unique_fps.append(fp)
                unique_texts.append(texts[idxs[0]])
            fetched = self._embed_unique(provider=provider, model=model, texts=unique_texts)
            for fp, vec in zip(unique_fps, fetched):
                if vec and self.cache:
                    self.cache.put(
                        fingerprint=fp,
                        provider=provider,
                        model=f"{model}::{provider_key}",
                        vector=vec,
                    )
                for i in misses[fp]:
                    out[i] = vec

        return [v or [] for v in out]

    def _embed_unique(self, *, provider: str, model: str, texts: Sequence[str]) -> List[List[float]]:
        if provider == "openai":
            return self._run_openai_batch_with_fallback(model=model, texts=texts)
        if provider == "gemini":
            return self._run_gemini_batch_with_fallback(model=model, texts=texts)
        # Safe fallback path for providers without stable batch semantics.
        return [self.embedding_client.embed_text(t) for t in texts]

    def _run_openai_batch_with_fallback(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        if self._batch_enabled:
            try:
                vecs = self._embed_openai_batch(model=model, texts=texts)
                if vecs:
                    self._batch_failures = 0
                    return vecs
                raise RuntimeError("empty openai batch embedding response")
            except Exception as e:
                self._batch_failures += 1
                if isinstance(e, ProviderDisabledBatchError):
                    self._provider_disabled_total += 1
                    self._batch_enabled = False
                if self._batch_failures >= max(1, int(self.config.batch_failure_limit)):
                    self._batch_enabled = False
                logger.warning(
                    "OpenAI embedding batch failed (%d/%d), fallback to single mode: %s",
                    self._batch_failures,
                    max(1, int(self.config.batch_failure_limit)),
                    e,
                )
                self._fallback_calls_total += 1
        else:
            self._fallback_calls_total += 1
        return [self.embedding_client.embed_text(t) for t in texts]

    def _is_retryable_http_status(self, status: int) -> bool:
        return status == 429 or status >= 500

    def _retry_http_call(self, fn: Callable[[], httpx.Response]) -> httpx.Response:
        max_attempts = max(1, int(self.config.retry_max_attempts or 1))
        base_ms = max(50, int(self.config.retry_base_delay_ms or 300))
        max_ms = max(base_ms, int(self.config.retry_max_delay_ms or 2000))
        attempt = 0
        delay_ms = base_ms
        last_err: Optional[BaseException] = None
        while attempt < max_attempts:
            try:
                self._retry_attempts_total += 1
                resp = fn()
                status = int(resp.status_code)
                if status >= 400 and (not self._is_retryable_http_status(status)):
                    raise NonRetryableBatchError(f"non-retryable http status={status}")
                if self._is_retryable_http_status(int(resp.status_code)):
                    resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                last_err = e
                if (not self._is_retryable_http_status(int(status))) or attempt >= (max_attempts - 1):
                    if not self._is_retryable_http_status(int(status)):
                        raise NonRetryableBatchError(str(e)) from e
                    raise RetryableBatchError(str(e)) from e
            except httpx.TransportError as e:
                last_err = e
                if attempt >= (max_attempts - 1):
                    raise RetryableBatchError(str(e)) from e
            jitter = 1.0 + (random.random() * 0.2)
            time.sleep(min(max_ms, int(delay_ms * jitter)) / 1000.0)
            delay_ms = min(max_ms, int(delay_ms * 2))
            attempt += 1
        if last_err is not None:
            raise last_err
        raise RuntimeError("retry failed")

    def _embed_openai_batch(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        if self.config.openai_async_batch_enabled:
            return self._embed_openai_async_batch(model=model, texts=texts)
        api_key = (self.config.openai_api_key or "").strip()
        if not api_key:
            raise ProviderDisabledBatchError("OPENAI_API_KEY missing for batch embeddings")
        base_url = (self.config.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        batch_size = max(1, int(self.config.batch_size))
        all_vectors: List[List[float]] = []

        with httpx.Client(timeout=self.config.timeout_s) as client:
            for start in range(0, len(texts), batch_size):
                chunk = list(texts[start : start + batch_size])
                payload = {"model": model, "input": chunk}
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "X-Embedding-Fingerprint": build_batch_fingerprint(
                        provider="openai",
                        model=model,
                        texts=chunk,
                    ),
                }
                resp = self._retry_http_call(
                    lambda: client.post(f"{base_url}/embeddings", json=payload, headers=headers)
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data") or []
                vectors = [(item or {}).get("embedding") or [] for item in items]
                if len(vectors) != len(chunk):
                    logger.warning(
                        "OpenAI batch embedding size mismatch: expect=%d got=%d",
                        len(chunk),
                        len(vectors),
                    )
                    raise NonRetryableBatchError("openai batch size mismatch")
                all_vectors.extend(vectors)
        return all_vectors

    def _run_gemini_batch_with_fallback(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        if self._batch_enabled:
            try:
                vecs = self._embed_gemini_batch(model=model, texts=texts)
                if vecs:
                    self._batch_failures = 0
                    return vecs
                raise RuntimeError("empty gemini batch embedding response")
            except Exception as e:
                self._batch_failures += 1
                if isinstance(e, ProviderDisabledBatchError):
                    self._provider_disabled_total += 1
                    self._batch_enabled = False
                if self._batch_failures >= max(1, int(self.config.batch_failure_limit)):
                    self._batch_enabled = False
                logger.warning(
                    "Gemini embedding batch failed (%d/%d), fallback to single mode: %s",
                    self._batch_failures,
                    max(1, int(self.config.batch_failure_limit)),
                    e,
                )
                self._fallback_calls_total += 1
        else:
            self._fallback_calls_total += 1
        return [self.embedding_client.embed_text(t) for t in texts]

    def _embed_gemini_batch(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        if self.config.gemini_async_batch_enabled:
            return self._embed_gemini_async_batch(model=model, texts=texts)

        api_key = (self.config.gemini_api_key or "").strip()
        if not api_key:
            raise ProviderDisabledBatchError("GEMINI_API_KEY missing for batch embeddings")
        base_url = (self.config.gemini_base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        batch_size = max(1, int(self.config.batch_size))
        all_vectors: List[List[float]] = []

        with httpx.Client(timeout=self.config.timeout_s) as client:
            for start in range(0, len(texts), batch_size):
                chunk = list(texts[start : start + batch_size])
                payload = {
                    "requests": [
                        {
                            "model": f"models/{model}" if not str(model).startswith("models/") else model,
                            "content": {"parts": [{"text": t}]},
                            "taskType": "RETRIEVAL_DOCUMENT",
                        }
                        for t in chunk
                    ]
                }
                url = f"{base_url}/models/{model}:batchEmbedContents"
                resp = self._retry_http_call(lambda: client.post(f"{url}?key={api_key}", json=payload))
                resp.raise_for_status()
                data = resp.json() or {}
                embeddings = data.get("embeddings") or []
                vectors = [((item or {}).get("values") or []) for item in embeddings]
                if len(vectors) != len(chunk):
                    raise NonRetryableBatchError("gemini batch size mismatch")
                all_vectors.extend(vectors)
        return all_vectors

    def _embed_gemini_async_batch(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        api_key = (self.config.gemini_api_key or "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing for async batch embeddings")
        base_url = (self.config.gemini_base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        batch_size = max(1, int(self.config.batch_size))
        all_vectors: List[List[float]] = []
        chunks = [list(texts[start : start + batch_size]) for start in range(0, len(texts), batch_size)]
        with httpx.Client(timeout=self.config.timeout_s) as client:
            tasks: List[Callable[[], List[List[float]]]] = []
            for chunk in chunks:
                tasks.append(
                    lambda c=chunk: self._run_gemini_async_chunk(
                        client=client,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        chunk=c,
                    )
                )
            grouped = self._run_with_concurrency(tasks, self._batch_concurrency)
            for vectors in grouped:
                all_vectors.extend(vectors)
        return all_vectors

    def _run_gemini_async_chunk(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        model: str,
        chunk: List[str],
    ) -> List[List[float]]:
        batch_fp = build_batch_fingerprint(provider="gemini", model=model, texts=chunk)
        batch_name, output_file_id = self._gemini_async_submit_and_wait(
            client=client,
            base_url=base_url,
            api_key=api_key,
            model=model,
            texts=chunk,
            batch_fingerprint=batch_fp,
        )
        lines = self._gemini_async_fetch_output_lines(
            client=client,
            base_url=base_url,
            api_key=api_key,
            output_file_id=output_file_id,
        )
        vectors = self._gemini_async_parse_output(lines=lines, texts=chunk, batch_name=batch_name)
        if len(vectors) != len(chunk):
            raise RuntimeError("gemini async batch output size mismatch")
        return vectors

    def _gemini_async_submit_and_wait(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        model: str,
        texts: Sequence[str],
        batch_fingerprint: str,
    ) -> Tuple[str, str]:
        if self.job_store is not None:
            existing = self.job_store.get(batch_fingerprint)
            if existing and existing.get("provider") == "gemini" and existing.get("batch_id"):
                status = str(existing.get("status") or "").lower()
                bid = str(existing.get("batch_id") or "")
                out = str(existing.get("output_file_id") or "")
                if status == "completed" and out:
                    self._resumed_jobs_total += 1
                    return bid, out
                if status in ("submitted", "running"):
                    try:
                        if not self.config.gemini_async_batch_wait:
                            raise RuntimeError(f"gemini batch {bid} still running and wait disabled")
                        # Reuse existing job id and wait for completion.
                        deadline = time.time() + max(1.0, float(self.config.gemini_async_timeout_s))
                        poll_interval = max(0.1, float(self.config.gemini_async_poll_interval_s))
                        while time.time() < deadline:
                            poll = client.get(f"{base_url}/{bid}?key={api_key}")
                            poll.raise_for_status()
                            body = poll.json() or {}
                            pstate = str(body.get("state") or "").strip().upper()
                            if pstate in {"SUCCEEDED", "COMPLETED", "DONE"}:
                                output_file = str(
                                    ((body.get("outputConfig") or {}).get("file"))
                                    or ((body.get("outputConfig") or {}).get("fileId"))
                                    or (((body.get("metadata") or {}).get("output") or {}).get("responsesFile"))
                                    or ""
                                ).strip()
                                if not output_file:
                                    raise RuntimeError(f"gemini batch {bid} completed without output file")
                                self.job_store.upsert(
                                    fingerprint=batch_fingerprint,
                                    provider="gemini",
                                    model=model,
                                    batch_id=bid,
                                    status="completed",
                                    output_file_id=output_file,
                                )
                                self._resumed_jobs_total += 1
                                return bid, output_file
                            if pstate in {"FAILED", "CANCELLED", "CANCELED", "EXPIRED"}:
                                raise RuntimeError(f"gemini batch {bid} {pstate}")
                            time.sleep(poll_interval)
                        raise RuntimeError(f"gemini batch {bid} timed out")
                    except Exception as e:
                        self.job_store.upsert(
                            fingerprint=batch_fingerprint,
                            provider="gemini",
                            model=model,
                            batch_id=bid,
                            status="failed",
                            error=str(e),
                        )

        jsonl_lines = []
        for i, text in enumerate(texts):
            jsonl_lines.append(
                json.dumps(
                    {
                        "key": f"req_{i}",
                        "request": {
                            "content": {"parts": [{"text": text}]},
                            "task_type": "RETRIEVAL_DOCUMENT",
                        },
                    },
                    ensure_ascii=False,
                )
            )
        files = {"file": ("memory_embeddings.jsonl", "\n".join(jsonl_lines).encode("utf-8"), "application/jsonl")}
        upload_url = f"{base_url.replace('/v1beta', '/upload/v1beta')}/files?uploadType=multipart&key={api_key}"
        up = client.post(upload_url, files=files)
        up.raise_for_status()
        uploaded = up.json() or {}
        file_id = str(uploaded.get("name") or (uploaded.get("file") or {}).get("name") or "").strip()
        if not file_id:
            raise RuntimeError("gemini async upload missing file id")

        batch_url = f"{base_url}/models/{model}:asyncBatchEmbedContent?key={api_key}"
        create_body = {"batch": {"displayName": "quentin-memory", "inputConfig": {"file_name": file_id}}}
        create = client.post(batch_url, json=create_body)
        create.raise_for_status()
        info = create.json() or {}
        batch_name = str(info.get("name") or "").strip()
        if not batch_name:
            raise RuntimeError("gemini async batch create missing name")
        if self.job_store is not None:
            self.job_store.upsert(
                fingerprint=batch_fingerprint,
                provider="gemini",
                model=model,
                batch_id=batch_name,
                status="submitted",
            )
        state = str(info.get("state") or "").strip().upper()
        out_id = str(
            ((info.get("outputConfig") or {}).get("file"))
            or ((info.get("outputConfig") or {}).get("fileId"))
            or (((info.get("metadata") or {}).get("output") or {}).get("responsesFile"))
            or ""
        ).strip()
        if state in {"SUCCEEDED", "COMPLETED", "DONE"} and out_id:
            if self.job_store is not None:
                self.job_store.upsert(
                    fingerprint=batch_fingerprint,
                    provider="gemini",
                    model=model,
                    batch_id=batch_name,
                    status="completed",
                    output_file_id=out_id,
                )
            return batch_name, out_id
        if not self.config.gemini_async_batch_wait:
            raise RuntimeError(f"gemini batch {batch_name} still {state or 'UNKNOWN'} and wait disabled")

        deadline = time.time() + max(1.0, float(self.config.gemini_async_timeout_s))
        poll_interval = max(0.1, float(self.config.gemini_async_poll_interval_s))
        while time.time() < deadline:
            poll = client.get(f"{base_url}/{batch_name}?key={api_key}")
            poll.raise_for_status()
            body = poll.json() or {}
            pstate = str(body.get("state") or "").strip().upper()
            if pstate in {"SUCCEEDED", "COMPLETED", "DONE"}:
                output_file = str(
                    ((body.get("outputConfig") or {}).get("file"))
                    or ((body.get("outputConfig") or {}).get("fileId"))
                    or (((body.get("metadata") or {}).get("output") or {}).get("responsesFile"))
                    or ""
                ).strip()
                if not output_file:
                    raise RuntimeError(f"gemini batch {batch_name} completed without output file")
                if self.job_store is not None:
                    self.job_store.upsert(
                        fingerprint=batch_fingerprint,
                        provider="gemini",
                        model=model,
                        batch_id=batch_name,
                        status="completed",
                        output_file_id=output_file,
                    )
                return batch_name, output_file
            if pstate in {"FAILED", "CANCELLED", "CANCELED", "EXPIRED"}:
                if self.job_store is not None:
                    self.job_store.upsert(
                        fingerprint=batch_fingerprint,
                        provider="gemini",
                        model=model,
                        batch_id=batch_name,
                        status="failed",
                        error=pstate,
                    )
                raise RuntimeError(f"gemini batch {batch_name} {pstate}")
            time.sleep(poll_interval)
        raise RuntimeError(f"gemini batch {batch_name} timed out")

    def _gemini_async_fetch_output_lines(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        output_file_id: str,
    ) -> List[dict]:
        file_id = output_file_id if output_file_id.startswith("files/") else f"files/{output_file_id}"
        resp = client.get(f"{base_url}/{file_id}:download?key={api_key}")
        resp.raise_for_status()
        lines: List[dict] = []
        for line in (resp.text or "").splitlines():
            s = line.strip()
            if s:
                lines.append(json.loads(s))
        return lines

    def _gemini_async_parse_output(
        self,
        *,
        lines: List[dict],
        texts: Sequence[str],
        batch_name: str,
    ) -> List[List[float]]:
        out: List[Optional[List[float]]] = [None] * len(texts)
        for line in lines:
            key = str(line.get("key") or line.get("custom_id") or line.get("request_id") or "").strip()
            if not key.startswith("req_"):
                continue
            try:
                idx = int(key.replace("req_", "", 1))
            except Exception:
                continue
            if idx < 0 or idx >= len(out):
                continue
            err = line.get("error") or ((line.get("response") or {}).get("error"))
            if err:
                msg = err.get("message") if isinstance(err, dict) else str(err)
                raise RuntimeError(f"gemini batch {batch_name} item failed: {msg}")
            vec = (
                ((line.get("embedding") or {}).get("values"))
                or (((line.get("response") or {}).get("embedding") or {}).get("values"))
                or []
            )
            out[idx] = vec
        if any(v is None for v in out):
            raise RuntimeError(f"gemini batch {batch_name} missing items in output")
        return [v or [] for v in out]

    def _embed_openai_async_batch(self, *, model: str, texts: Sequence[str]) -> List[List[float]]:
        api_key = (self.config.openai_api_key or "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing for async batch embeddings")
        base_url = (self.config.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"}
        batch_size = max(1, int(self.config.batch_size))
        all_vectors: List[List[float]] = []

        chunks = [list(texts[start : start + batch_size]) for start in range(0, len(texts), batch_size)]
        with httpx.Client(timeout=self.config.timeout_s) as client:
            tasks: List[Callable[[], List[List[float]]]] = []
            for chunk in chunks:
                tasks.append(
                    lambda c=chunk: self._run_openai_async_chunk(
                        client=client,
                        base_url=base_url,
                        model=model,
                        headers=headers,
                        chunk=c,
                    )
                )
            grouped = self._run_with_concurrency(tasks, self._batch_concurrency)
            for vectors in grouped:
                all_vectors.extend(vectors)

        return all_vectors

    def _run_openai_async_chunk(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        model: str,
        headers: Dict[str, str],
        chunk: List[str],
    ) -> List[List[float]]:
        batch_fp = build_batch_fingerprint(provider="openai", model=model, texts=chunk)
        batch_id, output_file_id = self._openai_async_submit_and_wait(
            client=client,
            base_url=base_url,
            model=model,
            headers=headers,
            texts=chunk,
            batch_fingerprint=batch_fp,
        )
        if not output_file_id:
            raise RuntimeError(f"openai batch {batch_id} completed without output file")
        lines = self._openai_async_fetch_output_lines(
            client=client,
            base_url=base_url,
            headers=headers,
            output_file_id=output_file_id,
        )
        vectors = self._openai_async_parse_output(lines=lines, texts=chunk)
        if len(vectors) != len(chunk):
            raise RuntimeError("openai async batch output size mismatch")
        return vectors

    def _openai_async_submit_and_wait(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        model: str,
        headers: Dict[str, str],
        texts: Sequence[str],
        batch_fingerprint: str,
    ) -> Tuple[str, str]:
        if self.job_store is not None:
            existing = self.job_store.get(batch_fingerprint)
            if existing and existing.get("provider") == "openai" and existing.get("batch_id"):
                batch_id = str(existing.get("batch_id") or "")
                status = str(existing.get("status") or "").lower()
                out = str(existing.get("output_file_id") or "")
                if status == "completed" and out:
                    self._resumed_jobs_total += 1
                    return batch_id, out
                if status in ("submitted", "running"):
                    try:
                        if not self.config.openai_async_batch_wait:
                            raise RuntimeError(f"openai batch {batch_id} still running and wait disabled")
                        out = wait_batch_output_file(
                            client=client,
                            base_url=base_url,
                            headers=headers,
                            batch_id=batch_id,
                            poll_interval_s=self.config.openai_async_poll_interval_s,
                            timeout_s=self.config.openai_async_timeout_s,
                        )
                        self.job_store.upsert(
                            fingerprint=batch_fingerprint,
                            provider="openai",
                            model=model,
                            batch_id=batch_id,
                            status="completed",
                            output_file_id=out,
                        )
                        self._resumed_jobs_total += 1
                        return batch_id, out
                    except Exception as e:
                        self.job_store.upsert(
                            fingerprint=batch_fingerprint,
                            provider="openai",
                            model=model,
                            batch_id=batch_id,
                            status="failed",
                            error=str(e),
                        )

        file_id = self._openai_async_upload_jsonl(
            client=client,
            base_url=base_url,
            headers=headers,
            model=model,
            texts=texts,
        )
        batch_id, status, output_file_id = create_batch_job(
            client=client,
            base_url=base_url,
            headers=headers,
            input_file_id=file_id,
        )
        if self.job_store is not None:
            self.job_store.upsert(
                fingerprint=batch_fingerprint,
                provider="openai",
                model=model,
                batch_id=batch_id,
                status="submitted",
            )
        if status == "completed" and output_file_id:
            if self.job_store is not None:
                self.job_store.upsert(
                    fingerprint=batch_fingerprint,
                    provider="openai",
                    model=model,
                    batch_id=batch_id,
                    status="completed",
                    output_file_id=output_file_id,
                )
            return batch_id, output_file_id
        if not self.config.openai_async_batch_wait:
            raise RuntimeError(f"openai batch {batch_id} still {status or 'unknown'} and wait disabled")
        out = wait_batch_output_file(
            client=client,
            base_url=base_url,
            headers=headers,
            batch_id=batch_id,
            poll_interval_s=self.config.openai_async_poll_interval_s,
            timeout_s=self.config.openai_async_timeout_s,
        )
        if self.job_store is not None:
            self.job_store.upsert(
                fingerprint=batch_fingerprint,
                provider="openai",
                model=model,
                batch_id=batch_id,
                status="completed",
                output_file_id=out,
            )
        return batch_id, out

    def _openai_async_upload_jsonl(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        headers: Dict[str, str],
        model: str,
        texts: Sequence[str],
    ) -> str:
        return upload_batch_file(
            client=client,
            base_url=base_url,
            headers=headers,
            model=model,
            texts=texts,
        )

    def _openai_async_fetch_output_lines(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        headers: Dict[str, str],
        output_file_id: str,
    ) -> List[dict]:
        return fetch_output_lines(
            client=client,
            base_url=base_url,
            headers=headers,
            output_file_id=output_file_id,
        )

    def _openai_async_parse_output(self, *, lines: List[dict], texts: Sequence[str]) -> List[List[float]]:
        out: List[Optional[List[float]]] = [None] * len(texts)
        for line in lines:
            custom_id = str(line.get("custom_id") or "").strip()
            if not custom_id.startswith("req_"):
                continue
            try:
                idx = int(custom_id.replace("req_", "", 1))
            except Exception:
                continue
            if idx < 0 or idx >= len(out):
                continue
            err = line.get("error") or ((line.get("response") or {}).get("body") or {}).get("error")
            if err:
                msg = err.get("message") if isinstance(err, dict) else str(err)
                raise RuntimeError(f"openai async batch item failed: {msg}")
            body = (line.get("response") or {}).get("body") or {}
            data = body.get("data") or []
            vec = ((data[0] or {}).get("embedding")) if data else []
            out[idx] = vec or []
        if any(v is None for v in out):
            raise RuntimeError("openai async batch missing items in output")
        return [v or [] for v in out]

    def status(self) -> Dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "provider_key": self.config.provider_key,
            "batch_enabled": bool(self._batch_enabled),
            "batch_failures": int(self._batch_failures),
            "batch_failure_limit": int(self.config.batch_failure_limit),
            "cache_enabled": self.cache is not None,
            "cache_entries": int(self.cache.count()) if self.cache is not None else 0,
            "openai_async_batch_enabled": bool(self.config.openai_async_batch_enabled),
            "gemini_async_batch_enabled": bool(self.config.gemini_async_batch_enabled),
            "account_tier": int(self.config.account_tier),
            "batch_concurrency": int(self._batch_concurrency),
            "retry_max_attempts": int(self.config.retry_max_attempts),
            "retry_base_delay_ms": int(self.config.retry_base_delay_ms),
            "retry_max_delay_ms": int(self.config.retry_max_delay_ms),
            "retry_attempts_total": int(self._retry_attempts_total),
            "fallback_calls_total": int(self._fallback_calls_total),
            "resumed_jobs_total": int(self._resumed_jobs_total),
            "provider_disabled_total": int(self._provider_disabled_total),
        }

    def _run_with_concurrency(self, tasks: Sequence[Callable[[], T]], limit: int) -> List[T]:
        if not tasks:
            return []
        resolved = max(1, min(int(limit or 1), len(tasks)))
        out: List[Optional[T]] = [None] * len(tasks)
        first_error: List[BaseException] = []
        lock = threading.Lock()
        next_idx = {"value": 0}

        def worker() -> None:
            while True:
                with lock:
                    if first_error:
                        return
                    idx = next_idx["value"]
                    next_idx["value"] += 1
                if idx >= len(tasks):
                    return
                try:
                    out[idx] = tasks[idx]()
                except BaseException as e:  # noqa: BLE001
                    with lock:
                        if not first_error:
                            first_error.append(e)
                    return

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(resolved)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if first_error:
            raise first_error[0]
        return [v for v in out if v is not None]


def resolve_batch_manager(
    *,
    embedding_client: EmbeddingClient,
    provider: str,
    model: str,
    provider_key: str,
    cache_path: str | Path,
    openai_base_url: str,
    openai_api_key: str,
    timeout_s: float,
    batch_size: int,
    openai_async_batch_enabled: bool,
    openai_async_batch_wait: bool,
    openai_async_poll_interval_s: float,
    openai_async_timeout_s: float,
    gemini_base_url: str,
    gemini_api_key: str,
    gemini_async_batch_enabled: bool,
    gemini_async_batch_wait: bool,
    gemini_async_poll_interval_s: float,
    gemini_async_timeout_s: float,
    account_tier: int,
    batch_concurrency: int,
    retry_max_attempts: int,
    retry_base_delay_ms: int,
    retry_max_delay_ms: int,
    job_store_path: str,
    enable_cache: bool,
) -> BatchEmbeddingManager:
    cache = EmbeddingCache(cache_path) if enable_cache else None
    cfg = BatchEmbeddingConfig(
        provider=provider,
        model=model,
        provider_key=provider_key,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        timeout_s=timeout_s,
        batch_size=batch_size,
        openai_async_batch_enabled=openai_async_batch_enabled,
        openai_async_batch_wait=openai_async_batch_wait,
        openai_async_poll_interval_s=openai_async_poll_interval_s,
        openai_async_timeout_s=openai_async_timeout_s,
        gemini_base_url=gemini_base_url,
        gemini_api_key=gemini_api_key,
        gemini_async_batch_enabled=gemini_async_batch_enabled,
        gemini_async_batch_wait=gemini_async_batch_wait,
        gemini_async_poll_interval_s=gemini_async_poll_interval_s,
        gemini_async_timeout_s=gemini_async_timeout_s,
        account_tier=account_tier,
        batch_concurrency=batch_concurrency,
        retry_max_attempts=retry_max_attempts,
        retry_base_delay_ms=retry_base_delay_ms,
        retry_max_delay_ms=retry_max_delay_ms,
        job_store_path=job_store_path,
    )
    return BatchEmbeddingManager(embedding_client=embedding_client, config=cfg, cache=cache)
