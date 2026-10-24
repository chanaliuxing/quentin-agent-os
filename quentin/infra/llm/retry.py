from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from quentin.llm.auth_profiles import get_auth_manager

logger = logging.getLogger(__name__)

T = TypeVar("T")

@dataclass
class RetryConfig:
    attempts: int = 3
    min_delay_ms: int = 300
    max_delay_ms: int = 30000
    jitter: float = 0.1
    retry_after_header_name: str = "Retry-After"

@dataclass
class RetryInfo:
    attempt: int
    max_attempts: int
    delay_ms: int
    error: Exception
    label: Optional[str] = None

class RetryStrategy:
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def classify_error(self, error: Exception) -> str:
        """
        Classifies error into categories: 
        'retryable', 'fatal', 'auth', 'quota', 'overloaded'
        """
        err_str = str(error).lower()
        
        # 1. Quota / Billing (Fatal for current key)
        if any(x in err_str for x in ["insufficient_quota", "billing", "credit_limit"]):
            return "quota"
            
        # 2. Auth (Fatal for current key)
        if any(x in err_str for x in ["invalid_api_key", "unauthorized", "401"]):
            return "auth"
            
        # 3. Overloaded (Retryable with backoff)
        if any(x in err_str for x in ["overloaded", "engine_overloaded", "503"]):
            return "overloaded"
            
        # 4. Rate Limit (Retryable with special backoff)
        if "429" in err_str or "too many requests" in err_str:
            return "rate_limit"
            
        # 5. Network / Timeout (Retryable)
        if any(x in err_str for x in ["timeout", "connect", "connection_error"]):
            return "retryable"
            
        return "fatal"

    def should_retry(self, error: Exception, attempt: int) -> bool:
        category = self.classify_error(error)
        # We only retry on transient issues
        return category in ("retryable", "overloaded", "rate_limit")

    async def execute(
        self,
        func: Callable[[], Any],
        label: Optional[str] = None,
        on_retry: Optional[Callable[[RetryInfo], None]] = None,
        on_fatal: Optional[Callable[[str, Exception], None]] = None,
        auth_profile_id: Optional[str] = None,
    ) -> Any:
        max_attempts = self.config.attempts
        last_error: Optional[Exception] = None
        auth_mgr = get_auth_manager()

        for attempt in range(1, max_attempts + 1):
            try:
                res = func()
                if asyncio.iscoroutine(res):
                    return await res
                return res
            except Exception as e:
                last_error = e
                category = self.classify_error(e)
                
                # P5: OpenClaw Parity - Report failure to the auth manager immediately
                if auth_profile_id:
                    auth_mgr.report_result(auth_profile_id, success=False, error_code=category)

                # If it's a fatal error (like auth/quota), don't waste time retrying
                if not self.should_retry(e, attempt):
                    logger.error(f"Fatal LLM Error [{category}]: {e}")
                    if on_fatal:
                        on_fatal(category, e)
                    break

                # Exponential backoff logic...
                delay = self.config.min_delay_ms * (2 ** (attempt - 1))
                if category == "rate_limit":
                    delay *= 2 # Extra patience for rate limits
                
                delay = min(delay, self.config.max_delay_ms)
                
                if on_retry:
                    on_retry(RetryInfo(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_ms=delay,
                        error=e,
                        label=label
                    ))
                else:
                    logger.warning(
                        "Retry %d/%d for %s in %dms due to: %s",
                        attempt, max_attempts, label or "task", delay, e
                    )
                
                await self.sleep_with_jitter(delay)

        if last_error:
            raise last_error
        raise RuntimeError(f"Retry failed for {label or 'task'}")

    async def sleep_with_jitter(self, delay_ms: int) -> None:
        """
        Sleep with jitter, async-friendly.
        """
        d = max(0, int(delay_ms))
        # +/- jitter% noise
        if self.config.jitter and self.config.jitter > 0:
            span = int(d * float(self.config.jitter))
            if span > 0:
                d = max(0, d + random.randint(-span, span))
        await asyncio.sleep(d / 1000.0)

# Provider-specific retry defaults
OLLAMA_RETRY_CONFIG = RetryConfig(
    attempts=3,
    min_delay_ms=500,
    max_delay_ms=15000,
    jitter=0.1
)

OPENAI_RETRY_CONFIG = RetryConfig(
    attempts=5,
    min_delay_ms=1000,
    max_delay_ms=60000,
    jitter=0.2
)
