import asyncio
import logging
import json
import os
import time
import gzip
import uuid
import hashlib
import inspect
import random
import queue
import threading
from typing import Any, Dict, List, Optional, Callable
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import httpx

from quentin.infra.llm.factory import ModelClientFactory
from quentin.infra.llm.base import ModelResponse
from quentin.llm.auth_profiles import get_auth_manager
from quentin.llm.context_budget import apply_context_budget
from quentin.infra.env_manager import env_bool
from quentin.infra.llm.failover import failover

logger = logging.getLogger(__name__)

# Re-usable thread pool for LLM bridging to avoid event loop conflicts
_LLM_EXECUTOR = ThreadPoolExecutor(max_workers=16)


_DIALECTS_BOOTSTRAPPED = False


def _append_llm_raw_history(entry: Dict[str, Any]) -> None:
    try:
        raw_log_path = os.path.join(os.getcwd(), "data/llm_raw_history.jsonl")
        os.makedirs(os.path.dirname(raw_log_path), exist_ok=True)
        try:
            max_mb = float(os.getenv("QUENTIN_LLM_RAW_HISTORY_MAX_MB", "128") or 128.0)
        except Exception:
            max_mb = 128.0
        if max_mb > 0 and os.path.exists(raw_log_path):
            size = os.path.getsize(raw_log_path)
            if size >= int(max_mb * 1024 * 1024):
                ts = int(time.time())
                rotated = raw_log_path.replace(".jsonl", f".{ts}.jsonl")
                os.replace(raw_log_path, rotated)
        with open(raw_log_path, "a", encoding="utf-8") as rf:
            rf.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _extract_http_error_detail(error: Exception) -> Optional[str]:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            text = str(error.response.text or "").strip()
            return text[:12000] if text else None
        except Exception:
            return None
    return None


def _sanitize_raw_response_for_log(raw_response: Any) -> Any:
    try:
        if isinstance(raw_response, dict) and "context" in raw_response:
            include_ctx = (os.getenv("QUENTIN_LLM_RAW_INCLUDE_OLLAMA_CONTEXT", "0") or "0").strip().lower()
            if include_ctx in {"1", "true", "yes", "on"}:
                return raw_response
            slim = dict(raw_response)
            slim.pop("context", None)
            return slim
    except Exception:
        pass
    return raw_response


def _attach_raw_response(entry: Dict[str, Any], raw_response: Any) -> None:
    safe_raw = _sanitize_raw_response_for_log(raw_response)
    try:
        raw_text = json.dumps(safe_raw, ensure_ascii=False, default=str)
    except Exception:
        raw_text = str(safe_raw)
    raw_bytes = raw_text.encode("utf-8", errors="replace")
    raw_size = len(raw_bytes)
    try:
        inline_limit = int(os.getenv("QUENTIN_LLM_RAW_INLINE_MAX_BYTES", "32768") or 32768)
    except Exception:
        inline_limit = 32768
    if raw_size <= max(1024, inline_limit):
        entry["raw_response"] = safe_raw
        return
    try:
        blobs_root = os.path.join(os.getcwd(), "data", "llm_raw_blobs")
        os.makedirs(blobs_root, exist_ok=True)
        use_gzip = (os.getenv("QUENTIN_LLM_RAW_BLOB_GZIP", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
        name = f"{int(time.time())}_{uuid.uuid4().hex}.json"
        if use_gzip:
            name += ".gz"
        full_path = os.path.join(blobs_root, name)
        if use_gzip:
            with gzip.open(full_path, "wt", encoding="utf-8") as bf:
                bf.write(raw_text)
        else:
            with open(full_path, "w", encoding="utf-8") as bf:
                bf.write(raw_text)
        try:
            preview_chars = int(os.getenv("QUENTIN_LLM_RAW_PREVIEW_CHARS", "1200") or 1200)
        except Exception:
            preview_chars = 1200
        entry["raw_response_preview"] = raw_text[:max(200, preview_chars)]
        entry["raw_response_ref"] = {
            "path": os.path.relpath(full_path, os.getcwd()),
            "bytes": raw_size,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "encoding": "utf-8",
            "compressed": use_gzip,
        }
    except Exception:
        # Never lose data if blob path fails.
        entry["raw_response"] = safe_raw


def _log_llm_raw_event(
    *,
    actor: str,
    provider: str,
    model: str,
    timeout_s: float,
    ok: bool,
    started_at: float,
    raw_response: Any = None,
    error: Optional[Exception] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    entry: Dict[str, Any] = {
        "ts": time.time(),
        "actor": actor or "unknown",
        "provider": provider,
        "model": model,
        "timeout_s": timeout_s,
        "ok": bool(ok),
        "latency_ms": int(max(0.0, (time.time() - started_at) * 1000)),
    }
    if isinstance(metadata, dict) and metadata:
        entry["metadata"] = metadata
    if raw_response is not None:
        _attach_raw_response(entry, raw_response)
    if error is not None:
        entry["error"] = str(error)
        http_detail = _extract_http_error_detail(error)
        if http_detail:
            entry["error_response_body"] = http_detail
    _append_llm_raw_history(entry)


def _resolve_llm_callsite() -> Dict[str, Any]:
    try:
        for frame_info in inspect.stack(context=0)[2:]:
            filename = str(frame_info.filename or "")
            if not filename:
                continue
            if filename.endswith("/quentin/llm/client.py"):
                continue
            return {
                "file": filename,
                "function": str(frame_info.function or ""),
                "lineno": int(frame_info.lineno or 0),
            }
    except Exception:
        pass
    return {}


def _looks_local_endpoint(url: Optional[str]) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = raw.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return True
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            return 16 <= second <= 31
        except Exception:
            return False
    return False


def _resolve_timeout_seconds(
    *,
    provider: str,
    explicit_timeout: Any,
    base_url: Optional[str] = None,
) -> float:
    if explicit_timeout is not None:
        return float(explicit_timeout)
    legacy = os.getenv("QUENTIN_LLM_TIMEOUT_S", "").strip()
    if legacy:
        return float(legacy)
    normalized = str(provider or "").strip().lower()
    is_local = normalized == "ollama" or _looks_local_endpoint(base_url)
    if is_local:
        return float(os.getenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", "240") or 240.0)
    return float(os.getenv("QUENTIN_LLM_TIMEOUT_REMOTE_S", "60") or 60.0)


def _build_http_timeout(*, timeout_s: float, base_url: Optional[str] = None, stream: bool = False) -> httpx.Timeout:
    total = max(1.0, float(timeout_s or 0.0))
    is_local = _looks_local_endpoint(base_url)
    try:
        local_read = float(os.getenv("QUENTIN_OLLAMA_READ_TIMEOUT_S", "20") or 20.0)
    except Exception:
        local_read = 20.0
    try:
        remote_read = float(os.getenv("QUENTIN_LLM_READ_TIMEOUT_REMOTE_S", "60") or 60.0)
    except Exception:
        remote_read = 60.0
    read_timeout = local_read if is_local else remote_read
    if read_timeout <= 0:
        resolved_read_timeout: float | None = None
    else:
        resolved_read_timeout = min(read_timeout, total)
    connect_timeout = min(10.0, total)
    write_timeout = min(30.0, total)
    pool_timeout = min(10.0, total)
    return httpx.Timeout(connect=connect_timeout, read=resolved_read_timeout, write=write_timeout, pool=pool_timeout)


def _normalize_ollama_base_url(raw: Optional[str]) -> str:
    base = (raw or os.getenv("LLM_BASE_URL", "http://localhost:11434")).strip()
    if not base:
        return "http://localhost:11434"
    base = base.rstrip("/")
    for suffix in ("/api/generate", "/api/chat"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _is_blank_llm_text(text: Any) -> bool:
    return str(text or "").strip() == ""


def _ollama_recovery_attempts() -> int:
    try:
        return max(1, int(os.getenv("QUENTIN_OLLAMA_RECOVERY_ATTEMPTS", "3") or 3))
    except Exception:
        return 3


def _ollama_recovery_model_sequence(primary_model: str) -> List[str]:
    primary = str(primary_model or "").strip()
    if not primary:
        return []
    seq = [primary]
    critic = str(os.getenv("LLM_MODEL_CRITIC", "") or "").strip()
    if critic and critic != primary:
        seq.append(critic)
    return seq


def _first_token_timeout_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("QUENTIN_OLLAMA_FIRST_TOKEN_TIMEOUT_S", "240") or 240.0))
    except Exception:
        return 240.0


def _is_recoverable_local_llm_error(error: Exception) -> bool:
    text = str(error or "").lower()
    markers = (
        "intervention_required:",
        "server disconnected without sending a response",
        "incomplete chunked read",
        "connection refused",
        "socket hang up",
        "backend_error",
        "peer closed connection",
        "empty_response",
        "first_token_timeout",
    )
    return any(marker in text for marker in markers)


def _sleep_brief_backoff(attempt: int) -> None:
    delay = min(8.0, 0.35 * (2 ** max(0, attempt - 1)))
    delay += random.uniform(0.0, 0.15)
    time.sleep(delay)


def _apply_prompt_dialect(
    *,
    provider: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    action_metadata: Optional[Dict[str, Any]],
) -> tuple[str, str]:
    """
    Apply PromptDialect plugins in one place (Blueprint v3 P3-C).
    Canonical env: QUENTIN_PROMPT_DIALECT=default
    """
    global _DIALECTS_BOOTSTRAPPED
    try:
        from quentin.llm.dialects import bootstrap_dialects, get_dialect_registry

        reg = get_dialect_registry()
        if not _DIALECTS_BOOTSTRAPPED and not reg.list_dialects():
            bootstrap_dialects(reg)
            _DIALECTS_BOOTSTRAPPED = True

        dialect_id = (os.getenv("QUENTIN_PROMPT_DIALECT", "default") or "default").strip()
        md = dict(action_metadata or {})
        sp, up, meta = reg.apply_id(
            dialect_id,
            provider=str(provider or "").strip().lower(),
            model_name=str(model_name or ""),
            system_prompt=str(system_prompt or ""),
            user_prompt=str(user_prompt or ""),
            metadata=md,
        )
        if action_metadata is not None and isinstance(meta, dict):
            action_metadata.update(meta)
        return sp, up
    except Exception:
        return system_prompt, user_prompt


def _http_retry_enabled() -> bool:
    return env_bool("QUENTIN_LLM_HTTP_RETRY", False)


def _post_with_retry(*, url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout_s: float) -> Dict[str, Any]:
    """
    Sync HTTP retry wrapper for call_llm's "direct httpx.Client" code paths.
    Default OFF to avoid surprising behavior changes.
    """
    if not _http_retry_enabled():
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        return resp.json() if hasattr(resp, "json") else {}

    import time

    last: Exception | None = None
    for attempt in range(1, 6):
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            return resp.json() if hasattr(resp, "json") else {}
        except Exception as e:
            last = e
            if not _is_rate_limit_error(e) and attempt >= 2:
                # Only retry non-rate-limit once.
                break
            time.sleep(min(10.0, 0.5 * (2 ** (attempt - 1))))
    if last:
        raise last
    return {}


class OllamaClient:
    """
    Lightweight Ollama adapter with Stream Intervention (OpenClaw Parity).
    """

    def __init__(self, cfg: Any):
        self.cfg = cfg

    @staticmethod
    def _is_local_ollama_base_url(base_url: str) -> bool:
        raw = str(base_url or "").strip().lower()
        if not raw:
            return False
        if "localhost" in raw or "127.0.0.1" in raw or "[::1]" in raw:
            return True
        return False

    @staticmethod
    def _stream_billing_bypass_enabled(base_url: str) -> bool:
        # Explicit global bypass still has highest priority.
        bypass_env = os.getenv("QUENTIN_BILLING_BYPASS", "0").strip().lower()
        if bypass_env in {"1", "true", "yes", "on"}:
            return True

        # For local Ollama, default to bypass unless explicitly forced on.
        local_enforce = os.getenv("QUENTIN_BILLING_ENFORCE_LOCAL_OLLAMA", "0").strip().lower()
        if OllamaClient._is_local_ollama_base_url(base_url) and local_enforce not in {"1", "true", "yes", "on"}:
            return True
        return False

    def complete(self, prompt: str, timeout: Optional[float] = None, history: List[str] = None) -> str:
        base_url = _normalize_ollama_base_url(getattr(self.cfg, "base_url", None))
        model = getattr(self.cfg, "name", None) or os.getenv("LLM_MODEL")
        
        # P5: Surgery Thirty-eight - Active Streaming Sentry
        from quentin.infra.llm.stream_sentry import StreamSentry
        sentry = StreamSentry(history_snippets=history)

        payload: Dict[str, Any] = {
            "model": str(model),
            "prompt": str(prompt or ""),
            "stream": True, # Always stream for intervention
        }
        
        # P5: Surgery Sixty-eight - Streaming Billing (OpenClaw Parity)
        from quentin.infra.billing.balance_manager import balance_manager
        user_id = os.getenv("QUENTIN_USER_ID", "default_user")
        billing_bypass = self._stream_billing_bypass_enabled(base_url=base_url)
        
        # P5: Surgery Ninety-five - Streaming Reply Polish (OpenClaw Parity)
        from quentin.infra.text.stream_cleaner import StreamCleaner
        cleaner = StreamCleaner()
        timeout_cfg = _build_http_timeout(timeout_s=float(timeout or 0.0), base_url=base_url, stream=True)
        self._last_raw_response = None
        events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        stop_event = threading.Event()

        def _stream_worker() -> None:
            try:
                with httpx.Client(timeout=timeout_cfg, headers={"Connection": "close"}) as client:
                    with client.stream("POST", f"{base_url}/api/generate", json=payload) as response:
                        if response.status_code != 200:
                            error_text = response.read().decode("utf-8", errors="ignore")
                            logger.error(f"Ollama stream error {response.status_code}: {error_text}")
                            events.put(("error", RuntimeError(f"Ollama error {response.status_code}: {error_text}")))
                            return

                        for line in response.iter_lines():
                            if stop_event.is_set():
                                return
                            if not line:
                                continue
                            chunk = json.loads(line)
                            events.put(("chunk", chunk))
                            if chunk.get("done"):
                                events.put(("done", None))
                                return
                events.put(("done", None))
            except Exception as e:  # noqa: BLE001
                events.put(("error", e))

        worker = threading.Thread(target=_stream_worker, daemon=True)
        worker.start()

        full_response: List[str] = []
        first_chunk_at = 0.0
        first_visible_at = 0.0
        started_at = time.time()
        while True:
            try:
                kind, payload_item = events.get(timeout=0.5)
            except queue.Empty:
                elapsed = time.time() - started_at
                if first_chunk_at <= 0.0 and elapsed >= _first_token_timeout_seconds():
                    stop_event.set()
                    raise RuntimeError(
                        f"first_token_timeout: no stream chunk received within {int(_first_token_timeout_seconds())}s"
                    )
                continue

            if kind == "error":
                stop_event.set()
                raise payload_item
            if kind == "done":
                break
            if kind != "chunk":
                continue

            chunk = payload_item
            self._last_raw_response = chunk
            if first_chunk_at <= 0.0:
                first_chunk_at = time.time()
            token = chunk.get("response", "")

            if not billing_bypass:
                if not balance_manager.deduct_realtime(user_id, tokens=1):
                    logger.critical(f"Billing: User {user_id} balance EXHAUSTED mid-stream. KILLING CONNECTION.")
                    stop_event.set()
                    raise RuntimeError("insufficient_funds: Your balance ran out during generation.")

            visible_delta = cleaner.process_token(token)

            intervention_reason = sentry.push_and_check(token)
            if intervention_reason:
                logger.error(f"LLM Intervention: {intervention_reason}. ABORTING STREAM.")
                stop_event.set()
                raise RuntimeError(f"intervention_required: {intervention_reason}")

            if visible_delta:
                if first_visible_at <= 0.0:
                    first_visible_at = time.time()
                full_response.append(visible_delta)

        repair_patch = cleaner.finalize()
        result = "".join(full_response) + repair_patch
        if _is_blank_llm_text(result):
            raise RuntimeError("empty_response: ollama returned blank visible output")
        return result

    def chat_with_tools(self, **kwargs) -> Dict[str, Any]:  # type: ignore[no-untyped-def]
        base_url = _normalize_ollama_base_url(getattr(self.cfg, "base_url", None))
        model = getattr(self.cfg, "name", None) or os.getenv("LLM_MODEL")
        if not model:
            raise ValueError("Environment variable LLM_MODEL is not set.")
        timeout_s = _resolve_timeout_seconds(
            provider="ollama",
            explicit_timeout=kwargs.get("timeout"),
            base_url=base_url,
        )

        messages = kwargs.get("messages") or []
        tools = kwargs.get("tools") or []

        payload: Dict[str, Any] = {
            "model": str(model),
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        try:
            num_ctx = int(os.getenv("LLM_OLLAMA_NUM_CTX", "8192"))
        except Exception:
            num_ctx = 8192
        payload["options"] = {"num_ctx": num_ctx}

        timeout_cfg = _build_http_timeout(timeout_s=timeout_s, base_url=base_url, stream=False)
        with httpx.Client(timeout=timeout_cfg, headers={"Connection": "close"}) as client:
            resp = client.post(f"{base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        try:
            setattr(self, "_last_raw_response", data)
        except Exception:
            pass

        msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        content = str((msg or {}).get("content") or "")
        tool_calls = (msg or {}).get("tool_calls") or []
        return {"content": content, "tool_calls": tool_calls, "raw": data}


def _guard_and_audit_start(**kwargs):  # type: ignore[no-untyped-def]
    # Hook point; unit tests monkeypatch.
    _ = kwargs
    return None, "action"


def _audit_finish(**kwargs) -> None:  # type: ignore[no-untyped-def]
    # Hook point; unit tests monkeypatch.
    _ = kwargs
    return None

def _is_rate_limit_error(e: Exception) -> bool:
    s = str(e).lower()
    return "429" in s or "rate limit" in s or "too many requests" in s

def call_llm(
    config: Any,
    user_prompt: str,
    system_prompt: str = "",
    *,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    action_metadata: Optional[Dict[str, Any]] = None,
    images: Optional[List[str]] = None,
    max_retries: int = 3,
    **kwargs
) -> str:
    if isinstance(config, str):
        model_id = config
    else:
        model_id = model_name or getattr(config, "name", None) or os.getenv("LLM_MODEL")
        if not model_id:
            raise ValueError("Environment variable LLM_MODEL is not set and no model provided.")

    prov = provider or getattr(config, "provider", None) or os.getenv("LLM_PROVIDER", "") or "ollama"
    auth_mgr = get_auth_manager()

    # Remote providers (unit-test friendly): use direct HTTP instead of ModelClientFactory.
    normalized = str(prov or "").strip().lower()
    # Offline/sandbox override: force stub regardless of route/provider selection.
    # This is critical for benchmark runs where network sockets are blocked.
    if str(os.getenv("QUENTIN_LLM_FORCE_STUB", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}:
        normalized = "stub"
    route_base_url = kwargs.get("base_url") or getattr(config, "base_url", None)
    if not route_base_url:
        if normalized in {"openai", "openrouter"}:
            route_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        elif normalized == "deepseek":
            route_base_url = os.getenv("DEEPSEEK_BASE_URL", "")
        elif normalized in {"gemini", "google"}:
            route_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    if normalized == "ollama":
        route_base_url = _normalize_ollama_base_url(route_base_url)
    timeout_s = _resolve_timeout_seconds(
        provider=normalized,
        explicit_timeout=kwargs.get("timeout"),
        base_url=route_base_url,
    )
    actor = str(kwargs.get("actor") or "unknown")
    trace_metadata = {"callsite": _resolve_llm_callsite()}

    # P3-C: Dialect plugins apply here so every call site is consistent.
    # For provider=stub (bench/offline), keep prompts unmodified so JSON payloads stay parseable.
    if normalized != "stub":
        system_prompt, user_prompt = _apply_prompt_dialect(
            provider=normalized,
            model_name=str(model_id or ""),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            action_metadata=action_metadata,
        )

    # Provider=stub: fully synchronous, thread-free path for sandbox/offline benchmarks.
    # Many call sites invoke call_llm from within an active asyncio loop (LaneOrchestrator.run_sync),
    # while some sandboxes disallow thread creation. The normal ModelClientFactory path uses a
    # ThreadPoolExecutor bridge, so we bypass it entirely here.
    if normalized == "stub":
        started = time.time()
        from quentin.infra.llm.stub_client import stub_generate_text

        try:
            out = stub_generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
            _log_llm_raw_event(
                actor=actor,
                provider="stub",
                model=str(model_id),
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=out,
                metadata=trace_metadata,
            )
            return str(out or "")
        except Exception as e:
            _log_llm_raw_event(
                actor=actor,
                provider="stub",
                model=str(model_id),
                timeout_s=timeout_s,
                ok=False,
                started_at=started,
                error=e,
                metadata=trace_metadata,
            )
            raise

    if normalized == "ollama":
        # Ollama local: apply context budget using the same `num_ctx` we'd send to Ollama.
        try:
            num_ctx = int(os.getenv("LLM_OLLAMA_NUM_CTX", "8192"))
        except Exception:
            num_ctx = 8192

        prompt_text = "\n\n".join([x for x in [system_prompt or "", user_prompt or ""] if x])
        prompt_text, guard = apply_context_budget(prompt_text=prompt_text, context_window_tokens=num_ctx)

        _, action_id = _guard_and_audit_start(
            provider="ollama",
            model=model_id,
            prompt_text=prompt_text,
            action_metadata=action_metadata,
            guard=guard,
        )
        try:
            started = time.time()
            attempts_per_model = _ollama_recovery_attempts()
            last_error: Exception | None = None
            out = ""
            used_model = str(model_id)
            last_raw_response: Any = None
            model_sequence = _ollama_recovery_model_sequence(str(model_id))
            for model_index, effective_model in enumerate(model_sequence, start=1):
                cfg_obj = config
                try:
                    if getattr(cfg_obj, "name", None) != effective_model:
                        from types import SimpleNamespace

                        cfg_obj = SimpleNamespace(
                            name=effective_model,
                            provider="ollama",
                            base_url=getattr(config, "base_url", None) or os.getenv("LLM_BASE_URL", "http://localhost:11434"),
                        )
                except Exception:
                    pass
                client = OllamaClient(cfg_obj)
                for attempt in range(1, attempts_per_model + 1):
                    try:
                        out = client.complete(prompt_text, timeout=timeout_s)
                        last_raw_response = getattr(client, "_last_raw_response", out)
                        if _is_blank_llm_text(out):
                            raise RuntimeError("empty_response: ollama returned blank text with done=true")
                        used_model = str(effective_model)
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        last_raw_response = getattr(client, "_last_raw_response", None)
                        if attempt >= attempts_per_model or not _is_recoverable_local_llm_error(e):
                            break
                        logger.warning(
                            "call_llm: recoverable ollama failure for model=%s attempt=%s/%s: %s",
                            effective_model,
                            attempt,
                            attempts_per_model,
                            e,
                        )
                        _sleep_brief_backoff(attempt)
                if last_error is None:
                    break
                if model_index < len(model_sequence) and _is_recoverable_local_llm_error(last_error):
                    logger.warning(
                        "call_llm: switching ollama recovery model from %s to %s after recoverable failure: %s",
                        effective_model,
                        model_sequence[model_index],
                        last_error,
                    )
                    continue
            if last_error is not None:
                raise last_error
            _log_llm_raw_event(
                actor=actor,
                provider="ollama",
                model=used_model,
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=last_raw_response if last_raw_response is not None else out,
                metadata=trace_metadata,
            )
            _audit_finish(action_id=action_id, ok=True, provider="ollama", model=used_model)
            return str(out or "")
        except Exception as e:
            _log_llm_raw_event(
                actor=actor,
                provider="ollama",
                model=str(model_id),
                timeout_s=timeout_s,
                ok=False,
                started_at=locals().get("started", time.time()),
                error=e,
                metadata=trace_metadata,
            )
            _audit_finish(action_id=action_id, ok=False, provider="ollama", model=model_id, error=str(e))
            raise

    if normalized in ("openai", "openrouter", "deepseek"):
        # OpenAI-compatible Chat Completions endpoint.
        if normalized == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY", "")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "").rstrip("/")
        else:
            api_key = os.getenv("OPENAI_API_KEY", "")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": user_prompt or ""},
            ],
        }
        started = time.time()
        try:
            data = _post_with_retry(
                url=f"{base_url}/chat/completions",
                payload=payload,
                headers=headers,
                timeout_s=timeout_s,
            )
            _log_llm_raw_event(
                actor=actor,
                provider=normalized,
                model=str(model_id),
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=data,
                metadata=trace_metadata,
            )
        except Exception as e:
            _log_llm_raw_event(
                actor=actor,
                provider=normalized,
                model=str(model_id),
                timeout_s=timeout_s,
                ok=False,
                started_at=started,
                error=e,
                metadata=trace_metadata,
            )
            raise
        choices = data.get("choices") or []
        msg = (choices[0] or {}).get("message") if choices else {}
        return str((msg or {}).get("content") or "")

    if normalized in ("gemini", "google"):
        api_key = os.getenv("GEMINI_API_KEY", "")
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        url = f"{base_url}/models/{model_id}:generateContent?key={api_key}"
        
        # P5: Schema Adapter
        from quentin.llm.provider_adapters.router import adapter_router
        adapter = adapter_router.get_adapter("gemini")
        
        raw_msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        if adapter:
            # transform_messages returns list of dicts with 'parts'
            transformed_msgs = adapter.transform_messages(raw_msgs)
            # Gemini HTTP API expects "contents": [...]
            # transform_messages output is compatible with contents list items
            payload = {"contents": transformed_msgs}
        else:
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": (system_prompt or "") + "\n" + (user_prompt or "")}]}
                ]
            }

        started = time.time()
        try:
            data = _post_with_retry(
                url=url,
                payload=payload,
                headers={},
                timeout_s=timeout_s,
            )
            _log_llm_raw_event(
                actor=actor,
                provider=normalized,
                model=str(model_id),
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=data,
                metadata=trace_metadata,
            )
        except Exception as e:
            _log_llm_raw_event(
                actor=actor,
                provider=normalized,
                model=str(model_id),
                timeout_s=timeout_s,
                ok=False,
                started_at=started,
                error=e,
                metadata=trace_metadata,
            )
            raise
        candidates = data.get("candidates") or []
        parts = (((candidates[0] or {}).get("content") or {}).get("parts") or []) if candidates else []
        return str((parts[0] or {}).get("text") or "")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    user_content = [{"type": "text", "text": user_prompt}]
    if images:
        for img in images:
            user_content.append({"type": "image", "image": img})
    messages.append({"role": "user", "content": user_content})

    # P5: Schema Adaptation (Messages)
    from quentin.llm.provider_adapters.router import adapter_router
    adapter = adapter_router.get_adapter(prov)
    if adapter:
        # Note: transform_messages expects Dicts, ensure format
        messages = adapter.transform_messages(messages)

    last_error = None
    for attempt in range(max_retries):
        profile = auth_mgr.get_best_profile(prov)
        started = time.time()
        
        call_kwargs = dict(kwargs)
        if profile:
            call_kwargs["api_key"] = profile.api_key
            call_kwargs["base_url"] = profile.base_url
            call_kwargs["profile_id"] = profile.profile_id
        call_kwargs.setdefault("timeout", timeout_s)
        
        # P5: Prevent argument collision
        call_kwargs.pop("provider", None)
        call_kwargs.pop("model_id", None)

        try:
            client = ModelClientFactory.create_client(model_id=model_id, provider=prov, **call_kwargs)
            
            def _run_sync_to_async():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(client.generate(messages))
                finally:
                    new_loop.close()

            # P5: Some sandboxed environments disallow thread creation (OSError: [Errno 1] Operation not permitted).
            # For provider=stub (and when explicitly requested), run the async client directly in this thread.
            force_direct = str(os.getenv("QUENTIN_LLM_DIRECT_EXEC", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
            if str(prov or "").strip().lower() == "stub" or force_direct:
                response: ModelResponse = _run_sync_to_async()
            else:
                # Submit with heartbeat (1 per minute)
                future = _LLM_EXECUTOR.submit(_run_sync_to_async)
                while not future.done():
                    print(".", end="", flush=True)
                    time.sleep(60.0)
                
                # Catch thread-level exceptions
                if future.exception():
                    err = future.exception()
                    print(f"\n[CRITICAL]: LLM Thread CRASHED: {err}", flush=True)
                    raise err
                
                response = future.result()
                print(" ")
            
            # P5: Record Usage
            try:
                from quentin.bootstrap.container import Container
                metrics = Container().metrics
                tokens = (response.usage.total_tokens if response.usage else 0) or 0
                metrics.record_usage(tokens=tokens)
            except Exception: pass

            _log_llm_raw_event(
                actor=actor,
                provider=str(prov),
                model=str(model_id),
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=response.text,
                metadata=trace_metadata,
            )

            if profile:
                auth_mgr.report_result(profile.profile_id, success=True)
                
            if action_metadata is not None:
                action_metadata["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                action_metadata["profile_id"] = profile.profile_id if profile else "default"
                
            return response.text

        except Exception as e:
            last_error = e
            _log_llm_raw_event(
                actor=actor,
                provider=str(prov),
                model=str(model_id),
                timeout_s=timeout_s,
                ok=False,
                started_at=started,
                error=e,
                metadata=trace_metadata,
            )
            if profile:
                error_code = 429 if _is_rate_limit_error(e) else 500
                auth_mgr.report_result(profile.profile_id, success=False, error_code=error_code)
            
            # P5: Use Failover Strategy Logic
            if not failover.should_retry(e, attempt):
                raise
            
            delay = failover.get_delay(attempt)
            print(f"\nLLM attempt {attempt+1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)

    return f"ERROR: LLM Call Failed: {last_error}"

def call_llm_with_tools(
    config: Any,
    *,
    system_prompt: str,
    user_prompt: str,
    tools: List[Dict[str, Any]],
    **kwargs
) -> Dict[str, Any]:
    prov = (kwargs.get("provider") or getattr(config, "provider", None) or os.getenv("LLM_PROVIDER", "ollama") or "ollama").strip().lower()
    model_id = kwargs.get("model_name") or getattr(config, "name", None) or os.getenv("LLM_MODEL")
    if not model_id:
        raise ValueError("Environment variable LLM_MODEL is not set.")
    actor = str(kwargs.get("actor") or "unknown")
    base_url = getattr(config, "base_url", None) or os.getenv("LLM_BASE_URL", "http://localhost:11434")
    timeout_s = _resolve_timeout_seconds(
        provider=prov,
        explicit_timeout=kwargs.get("timeout"),
        base_url=base_url,
    )
    trace_metadata = {"callsite": _resolve_llm_callsite()}

    # Non-ollama providers: fallback to plain text generation.
    if prov != "ollama":
        text = call_llm(
            config,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            provider=prov,
            model_name=str(model_id),
            timeout=timeout_s,
            actor=actor,
        )
        return {"message": {"content": text}, "tool_calls": []}

    explicit_tool_model = (os.getenv("LLM_TOOL_MODEL", "") or "").strip()
    text_model = (os.getenv("LLM_TEXT_MODEL", "") or "").strip() or os.getenv("LLM_MODEL")
    primary_model = explicit_tool_model or str(model_id)
    if not explicit_tool_model and "vl" in primary_model.lower() and text_model:
        primary_model = text_model

    try:
        num_ctx = int(os.getenv("LLM_OLLAMA_NUM_CTX", "8192"))
    except Exception:
        num_ctx = 8192

    # IMPORTANT: for tool-calling, keep system/user roles instead of concatenating into one user message.
    # Many local models (incl. Qwen) follow tool-calling constraints far more reliably when rules are in "system".
    from quentin.llm.context_budget import estimate_tokens

    sys = str(system_prompt or "")
    usr = str(user_prompt or "")

    # Budget user content while preserving system instructions.
    sys_tokens = estimate_tokens(sys)
    # Keep a buffer for tool schemas + reply tokens.
    reserve = int(os.getenv("LLM_RESERVE_TOKENS", "1024") or 1024)
    user_budget = max(256, int(num_ctx) - int(sys_tokens) - reserve)
    usr, _guard = apply_context_budget(prompt_text=usr, context_window_tokens=user_budget)

    messages: List[Dict[str, Any]] = []
    if sys.strip():
        messages.append({"role": "system", "content": sys})
    if usr.strip() or not messages:
        messages.append({"role": "user", "content": usr})

    def _run(model: str) -> Dict[str, Any]:
        from types import SimpleNamespace

        cfg_obj = SimpleNamespace(name=model, provider="ollama", base_url=base_url)
        client = OllamaClient(cfg_obj)
        started = time.time()
        try:
            result = client.chat_with_tools(messages=messages, tools=tools, timeout=timeout_s)
            _log_llm_raw_event(
                actor=actor,
                provider="ollama",
                model=str(model),
                timeout_s=timeout_s,
                ok=True,
                started_at=started,
                raw_response=getattr(client, "_last_raw_response", result),
                metadata=trace_metadata,
            )
            return result
        except Exception as e:
            _log_llm_raw_event(
                actor=actor,
                provider="ollama",
                model=str(model),
                timeout_s=timeout_s,
                ok=False,
                started_at=started,
                error=e,
                metadata=trace_metadata,
            )
            raise

    try:
        return _run(primary_model)
    except Exception as e:
        s = str(e).lower()
        if ("does not support tools" in s or "support tools" in s or "unsupported" in s) and text_model and primary_model != text_model:
            return _run(text_model)
        raise
