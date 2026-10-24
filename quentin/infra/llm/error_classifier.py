from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional, Set

# Ported from OpenClaw's error classification constants
CONTEXT_WINDOW_TOO_SMALL_RE = re.compile(r"context window.*(too small|minimum is)", re.IGNORECASE)
CONTEXT_OVERFLOW_HINT_RE = re.compile(
    r"context.*overflow|context window.*(too (?:large|long)|exceed|over|limit|max(?:imum)?|requested|sent|tokens)|(?:prompt|request|input).*(too (?:large|long)|exceed|over|limit|max(?:imum)?)|maximum context length",
    re.IGNORECASE
)

RATE_LIMIT_RE = re.compile(r"rate[_ ]limit|too many requests|429|exceeded your current quota|resource has been exhausted|quota exceeded|resource_exhausted|usage limit", re.IGNORECASE)
AUTH_RE = re.compile(r"invalid[_ ]?api[_ ]?key|incorrect api key|invalid token|authentication|re-authenticate|oauth token refresh failed|unauthorized|forbidden|access denied|expired|token has expired|\b401\b|\b403\b|no credentials found|no api key found", re.IGNORECASE)
OVERLOADED_RE = re.compile(r"overloaded_error|\"type\"\s*:\s*\"overloaded_error\"|overloaded|service unavailable|503", re.IGNORECASE)
TIMEOUT_RE = re.compile(r"timeout|timed out|deadline exceeded|context deadline exceeded", re.IGNORECASE)
BILLING_RE = re.compile(r"\b402\b|payment required|insufficient credits|credit balance|plans & billing|insufficient_quota", re.IGNORECASE)

class ErrorClassifier:
    """
    P5: Ported from OpenClaw's pi-embedded-helpers/errors.ts.
    Advanced error classification for strategic retries and failover.
    """

    @staticmethod
    def is_context_overflow(error_message: Optional[str]) -> bool:
        if not error_message:
            return False
        
        msg = str(error_message).lower()
        
        # Exact markers
        if any(x in msg for x in [
            "request_too_large",
            "request exceeds the maximum size",
            "context length exceeded",
            "maximum context length",
            "prompt is too long",
            "exceeds model context window",
            "context overflow",
            "413"
        ]):
            return True
            
        # Pattern match
        if CONTEXT_OVERFLOW_HINT_RE.search(error_message):
            return True
            
        return False

    @staticmethod
    def is_compaction_failure(error_message: Optional[str]) -> bool:
        if not error_message or not ErrorClassifier.is_context_overflow(error_message):
            return False
        
        msg = str(error_message).lower()
        return any(x in msg for x in ["summarization failed", "auto-compaction", "compaction failed", "compaction"])

    @staticmethod
    def classify(error_message: Optional[str]) -> str:
        """
        Classifies error into high-level categories for decision making.
        """
        if not error_message:
            return "unknown"
            
        msg = str(error_message)
        
        if ErrorClassifier.is_context_overflow(msg):
            return "context_overflow"
            
        if RATE_LIMIT_RE.search(msg):
            return "rate_limit"
            
        if AUTH_RE.search(msg):
            return "auth"
            
        if OVERLOADED_RE.search(msg):
            return "overloaded"
            
        if TIMEOUT_RE.search(msg):
            return "timeout"
            
        if BILLING_RE.search(msg):
            return "billing"
            
        return "fatal"

    @staticmethod
    def pick_fallback_thinking_level(error_message: Optional[str], attempted: Set[str]) -> Optional[str]:
        """
        P5: Ported from OpenClaw's thinking level fallback logic.
        Extracts supported values from error messages like "supported values are: 'off', 'low'..."
        """
        if not error_message:
            return None
            
        # Look for "supported values are: ..." or "supported values: ..."
        match = re.search(r"supported values(?: are)?:?\s*([^\n.]+)", error_message, re.IGNORECASE)
        if not match:
            return None
            
        fragment = match.group(1)
        # Try finding quoted values first
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", fragment)
        if quoted:
            supported = [v.strip() for v in quoted if v.strip()]
        else:
            # Fallback to splitting by comma or 'and'
            supported = [v.strip() for v in re.split(r",|\band\b", fragment, flags=re.IGNORECASE) if v.strip()]
            
        for level in supported:
            if level not in attempted:
                return level
                
        return None

# Global instance
error_classifier = ErrorClassifier()
