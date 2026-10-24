from __future__ import annotations
import logging
from typing import Optional, Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")

class FailoverStrategy:
    """
    Tier 0 Failover Logic.
    Ported from OpenClaw's retry/failover logic.
    """
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def should_retry(self, error: Exception, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
            
        s = str(error).lower()
        # Retry on network/rate limits
        if "429" in s or "rate limit" in s or "timeout" in s or "connection" in s:
            return True
            
        # Do not retry on auth errors or bad requests
        if "401" in s or "403" in s or "invalid api key" in s:
            return False
            
        return True

    def get_delay(self, attempt: int) -> float:
        # Exponential backoff
        return self.base_delay * (2 ** attempt)

    async def run(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        last_err = None
        for i in range(self.max_retries + 1):
            try:
                res = func(*args, **kwargs)
                # Support both sync and async callables.
                if hasattr(res, "__await__"):
                    return await res
                return res
            except Exception as e:
                last_err = e
                if not self.should_retry(e, i):
                    raise
                
                delay = self.get_delay(i)
                logger.warning(f"Failover: Attempt {i+1} failed ({e}). Retrying in {delay}s...")
                import asyncio
                await asyncio.sleep(delay)
        
        raise last_err

# Global instance
failover = FailoverStrategy()
