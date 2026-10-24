from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Literal


FailoverReason = Literal[
    "rate_limit",
    "billing",
    "auth",
    "timeout",
    "format",
    "context_overflow",
    "registry_error",
]


_RATE_LIMIT_PATTERNS = [
    r"rate limit",
    r"too many requests",
    r"overloaded",
    r"429",
    r"capacity",
]
_BILLING_PATTERNS = [
    r"billing",
    r"quota",
    r"insufficient_quota",
    r"payment required",
    r"402",
]
_AUTH_PATTERNS = [
    r"unauthorized",
    r"forbidden",
    r"invalid api key",
    r"invalid token",
    r"401",
    r"403",
]
_TIMEOUT_PATTERNS = [
    r"timeout",
    r"timed out",
    r"deadline exceeded",
    r"context deadline exceeded",
    r"408",
]
_FORMAT_PATTERNS = [
    r"invalid request",
    r"schema",
    r"tool",
    r"format",
    r"400",
    r"unexpected token",
    r"json",
]
_CONTEXT_PATTERNS = [
    r"context",
    r"prompt is too long",
    r"maximum context length",
    r"request size exceeds",
    r"413",
]
_REGISTRY_PATTERNS = [
    r"model not found",
    r"unknown model",
    r"tool not found",
    r"registry declaration error",
    r"404",
]


def _matches(patterns: list[str], text: str) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def classify_failover_reason(raw: str) -> Optional[FailoverReason]:
    text = (raw or "").strip()
    if not text:
        return None
    if _matches(_RATE_LIMIT_PATTERNS, text):
        return "rate_limit"
    if _matches(_BILLING_PATTERNS, text):
        return "billing"
    if _matches(_AUTH_PATTERNS, text):
        return "auth"
    if _matches(_TIMEOUT_PATTERNS, text):
        return "timeout"
    if _matches(_FORMAT_PATTERNS, text):
        return "format"
    if _matches(_CONTEXT_PATTERNS, text):
        return "context_overflow"
    if _matches(_REGISTRY_PATTERNS, text):
        return "registry_error"
    return None


@dataclass
class FailoverError(Exception):
    message: str
    reason: FailoverReason
    status: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    profile_id: Optional[str] = None

    def __str__(self) -> str:
        return self.message


def coerce_failover_error(
    err: Exception,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> Optional[FailoverError]:
    message = str(err)
    reason = classify_failover_reason(message)
    if not reason:
        return None
    status = _infer_status_from_reason(reason)
    return FailoverError(
        message=message,
        reason=reason,
        status=status,
        provider=provider,
        model=model,
        profile_id=profile_id,
    )


def _infer_status_from_reason(reason: FailoverReason) -> Optional[int]:
    if reason == "billing":
        return 402
    if reason == "rate_limit":
        return 429
    if reason == "auth":
        return 401
    if reason == "timeout":
        return 408
    if reason == "format":
        return 400
    if reason == "context_overflow":
        return 413
    return None
