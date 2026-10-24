from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Protocol, Optional

import httpx
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    def embed_text(self, text: str) -> List[float]: ...
    @property
    def dim(self) -> int: ...


@dataclass
class EmbeddingConfig:
    provider: str = "ollama"  # "ollama" | "openai" | "gemini" | "disabled" | "fallback"
    model: str = "nomic-embed-text"
    base_url: str = "http://localhost:11434"
    expected_dim: int = 768   # MUST match pgvector schema
    timeout: float = 10.0
    retries: int = 1


class EmbeddingHealthRegistry:
    def __init__(self) -> None:
        self._stats: Dict[str, Dict[str, object]] = {}

    def record_success(self, provider: str, latency_ms: float) -> None:
        s = self._stats.setdefault(
            provider,
            {
                "provider": provider,
                "success": 0,
                "failure": 0,
                "consecutive_failures": 0,
                "last_success_at": None,
                "last_failure_at": None,
                "last_error": None,
                "last_latency_ms": None,
            },
        )
        s["success"] = int(s.get("success") or 0) + 1
        s["consecutive_failures"] = 0
        s["last_success_at"] = now_iso()
        s["last_latency_ms"] = float(latency_ms)

    def record_failure(self, provider: str, error: Exception) -> None:
        s = self._stats.setdefault(
            provider,
            {
                "provider": provider,
                "success": 0,
                "failure": 0,
                "consecutive_failures": 0,
                "last_success_at": None,
                "last_failure_at": None,
                "last_error": None,
                "last_latency_ms": None,
            },
        )
        s["failure"] = int(s.get("failure") or 0) + 1
        s["consecutive_failures"] = int(s.get("consecutive_failures") or 0) + 1
        s["last_failure_at"] = now_iso()
        s["last_error"] = str(error)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        return {k: dict(v) for k, v in self._stats.items()}


_EMBEDDING_HEALTH = EmbeddingHealthRegistry()


def get_embedding_health_snapshot() -> Dict[str, Dict[str, object]]:
    return _EMBEDDING_HEALTH.snapshot()


class DisabledEmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig):
        self._cfg = cfg

    def embed_text(self, text: str) -> List[float]:
        return []

    @property
    def dim(self) -> int:
        return self._cfg.expected_dim


class SyncOllamaEmbeddingClient:
    """
    Synchronous wrapper for Ollama embeddings to be used in sync MemoryFabric.
    """

    def __init__(self, cfg: EmbeddingConfig):
        self._cfg = cfg

    def embed_text(self, text: str) -> List[float]:
        try:
            start = time.perf_counter()
            with httpx.Client(timeout=self._cfg.timeout) as client:
                response = client.post(
                    f"{self._cfg.base_url}/api/embeddings",
                    json={"model": self._cfg.model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                vec = data.get("embedding", [])

                if not vec:
                    raise ValueError("Empty embedding returned")

                if len(vec) != self._cfg.expected_dim:
                    logger.warning(
                        "Embedding dim mismatch: got %d, expected %d. Model: %s",
                        len(vec),
                        self._cfg.expected_dim,
                        self._cfg.model,
                    )
                _EMBEDDING_HEALTH.record_success(self._cfg.provider, (time.perf_counter() - start) * 1000)
                return vec
        except Exception as e:
            _EMBEDDING_HEALTH.record_failure(self._cfg.provider, e)
            logger.error("Embedding generation failed: %s", e)
            raise e

    @property
    def dim(self) -> int:
        return self._cfg.expected_dim


class SyncOpenAIEmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig, api_key: str):
        self._cfg = cfg
        self._api_key = api_key

    def embed_text(self, text: str) -> List[float]:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {"model": self._cfg.model, "input": text}
        try:
            start = time.perf_counter()
            with httpx.Client(timeout=self._cfg.timeout) as client:
                response = client.post(f"{self._cfg.base_url}/embeddings", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                items = data.get("data") or []
                vec = (items[0] or {}).get("embedding") if items else []
                if not vec:
                    raise ValueError("Empty embedding returned")
                _EMBEDDING_HEALTH.record_success(self._cfg.provider, (time.perf_counter() - start) * 1000)
                return vec
        except Exception as e:
            _EMBEDDING_HEALTH.record_failure(self._cfg.provider, e)
            raise e

    @property
    def dim(self) -> int:
        return self._cfg.expected_dim


class SyncGeminiEmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig, api_key: str):
        self._cfg = cfg
        self._api_key = api_key

    def embed_text(self, text: str) -> List[float]:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini embeddings")
        url = f"{self._cfg.base_url}/models/{self._cfg.model}:embedContent"
        payload = {"content": {"parts": [{"text": text}]}}
        try:
            start = time.perf_counter()
            with httpx.Client(timeout=self._cfg.timeout) as client:
                response = client.post(f"{url}?key={self._api_key}", json=payload)
                response.raise_for_status()
                data = response.json()
                vec = ((data.get("embedding") or {}).get("values")) or []
                if not vec:
                    raise ValueError("Empty embedding returned")
                _EMBEDDING_HEALTH.record_success(self._cfg.provider, (time.perf_counter() - start) * 1000)
                return vec
        except Exception as e:
            _EMBEDDING_HEALTH.record_failure(self._cfg.provider, e)
            raise e

    @property
    def dim(self) -> int:
        return self._cfg.expected_dim


class FallbackEmbeddingClient:
    def __init__(self, providers: List[EmbeddingClient], provider_names: List[str], retries: List[int]):
        self._providers = providers
        self._provider_names = provider_names
        self._retries = retries

    def embed_text(self, text: str) -> List[float]:
        last_error: Optional[Exception] = None
        for idx, provider in enumerate(self._providers):
            name = self._provider_names[idx]
            attempts = max(1, int(self._retries[idx]))
            for _ in range(attempts):
                try:
                    vec = provider.embed_text(text)
                    if vec:
                        return vec
                    last_error = ValueError("Empty embedding returned")
                    _EMBEDDING_HEALTH.record_failure(name, last_error)
                except Exception as e:
                    last_error = e
        if last_error is not None:
            logger.warning("All embedding providers failed: %s", last_error)
        return []

    @property
    def dim(self) -> int:
        for p in self._providers:
            return p.dim
        return 0


def create_embedding_client_from_env() -> EmbeddingClient:
    """Factory to auto-configure from env vars."""
    provider = os.getenv("MEM_EMBED_PROVIDER", "disabled").strip().lower()
    model = os.getenv("MEM_EMBED_MODEL", "nomic-embed-text")
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    try:
        dim = int(os.getenv("MEM_EMBED_DIM", "768"))
    except ValueError:
        dim = 768
    timeout = float(os.getenv("MEM_EMBED_TIMEOUT", "10.0"))
    retries = int(os.getenv("MEM_EMBED_RETRIES", "1"))

    cfg = EmbeddingConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        expected_dim=dim,
        timeout=timeout,
        retries=retries,
    )

    def _build_client(p: str) -> Optional[EmbeddingClient]:
        p = p.strip().lower()
        if p == "ollama":
            return SyncOllamaEmbeddingClient(cfg)
        if p == "openai":
            openai_key = os.getenv("OPENAI_API_KEY", "")
            openai_model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
            openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            openai_timeout = float(os.getenv("OPENAI_EMBED_TIMEOUT", str(timeout)))
            openai_retries = int(os.getenv("OPENAI_EMBED_RETRIES", str(retries)))
            openai_cfg = EmbeddingConfig(
                provider="openai",
                model=openai_model,
                base_url=openai_base,
                expected_dim=dim,
                timeout=openai_timeout,
                retries=openai_retries,
            )
            return SyncOpenAIEmbeddingClient(openai_cfg, openai_key)
        if p == "gemini":
            gemini_key = os.getenv("GEMINI_API_KEY", "")
            gemini_model = os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004")
            gemini_base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
            gemini_timeout = float(os.getenv("GEMINI_EMBED_TIMEOUT", str(timeout)))
            gemini_retries = int(os.getenv("GEMINI_EMBED_RETRIES", str(retries)))
            gemini_cfg = EmbeddingConfig(
                provider="gemini",
                model=gemini_model,
                base_url=gemini_base,
                expected_dim=dim,
                timeout=gemini_timeout,
                retries=gemini_retries,
            )
            return SyncGeminiEmbeddingClient(gemini_cfg, gemini_key)
        if p == "disabled":
            return DisabledEmbeddingClient(cfg)
        return None

    if provider in ("fallback", "auto") or "," in provider:
        fallback_list = os.getenv("MEM_EMBED_FALLBACKS", provider)
        if fallback_list in ("fallback", "auto"):
            fallback_list = "openai,gemini,ollama,disabled"
        parts = [p for p in fallback_list.split(",") if p.strip()]
        clients: List[EmbeddingClient] = []
        names: List[str] = []
        retries_list: List[int] = []
        for p in parts:
            client = _build_client(p)
            if client is None:
                continue
            clients.append(client)
            names.append(p.strip().lower())
            retries_list.append(int(os.getenv(f"{p.strip().upper()}_EMBED_RETRIES", str(retries))))
        if clients:
            return FallbackEmbeddingClient(clients, names, retries_list)
        return DisabledEmbeddingClient(cfg)

    single = _build_client(provider)
    if single is not None:
        return single
    return DisabledEmbeddingClient(cfg)
