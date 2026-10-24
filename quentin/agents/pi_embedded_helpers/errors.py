from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from quentin.infra.llm.error_classifier import error_classifier


@dataclass
class ErrorTaxonomy:
    kind: str
    retryable: bool
    reflection_weight: str  # low | medium | high | critical
    hint: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_error_taxonomy(error_message: Optional[str]) -> ErrorTaxonomy:
    kind = error_classifier.classify(error_message)
    mapping = {
        "context_overflow": (True, "high", "Compact context and retry with reduced payload."),
        "rate_limit": (True, "medium", "Backoff and retry later."),
        "timeout": (True, "medium", "Retry with simpler tool sequence."),
        "overloaded": (True, "medium", "Retry with fallback model/provider."),
        "auth": (False, "critical", "Fix credentials/auth profile before retry."),
        "billing": (False, "critical", "Restore provider budget/credits before retry."),
        "fatal": (False, "high", "Treat as non-transient; require reflection-guided replanning."),
        "unknown": (False, "medium", "Collect more diagnostics before retry."),
    }
    retryable, weight, hint = mapping.get(kind, (False, "medium", "Unknown error; inspect logs."))
    return ErrorTaxonomy(kind=kind, retryable=retryable, reflection_weight=weight, hint=hint)

