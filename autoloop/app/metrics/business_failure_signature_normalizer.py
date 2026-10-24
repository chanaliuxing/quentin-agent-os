from __future__ import annotations

import re
from typing import Any


def normalize_business_failure_signature(
    *,
    primary_failure_type: str,
    first_failure_stage: str,
    missing_artifacts: list[str] | None = None,
    grader_results: dict[str, str] | None = None,
    failure_events: list[dict[str, Any]] | None = None,
) -> str:
    tokens: list[str] = []
    failure_type = _clean(primary_failure_type) or "unknown_failure"
    stage = _clean(first_failure_stage) or "unknown_stage"
    tokens.append(failure_type)
    tokens.append(stage)
    artifacts = sorted({_clean(item) for item in (missing_artifacts or []) if _clean(item)})
    if artifacts:
        tokens.append("artifacts:" + "|".join(artifacts[:5]))
    grader_pairs = sorted(
        f"{_clean(key)}:{_clean(value)}"
        for key, value in (grader_results or {}).items()
        if _clean(key) and _clean(value) and _clean(value) != "pass"
    )
    if grader_pairs:
        tokens.append("grader:" + "|".join(grader_pairs[:5]))
    event_types = sorted(
        {
            _clean(str(item.get("cause_type", "")))
            for item in (failure_events or [])
            if isinstance(item, dict) and _clean(str(item.get("cause_type", "")))
        }
    )
    if event_types:
        tokens.append("events:" + "|".join(event_types[:5]))
    return _sanitize(":".join(tokens))


def infer_taxonomy_candidate_name(
    *,
    signature: str,
    primary_failure_type: str,
) -> str:
    normalized_signature = _sanitize(signature)
    if not normalized_signature:
        normalized_signature = "unknown_pattern"
    normalized_signature = normalized_signature.replace(":", "_").replace("|", "_")
    normalized_signature = re.sub(r"_+", "_", normalized_signature).strip("_")
    prefix = _clean(primary_failure_type).upper() or "BUSINESS"
    if prefix.startswith("BUSINESS_"):
        pass
    elif prefix.startswith("AGENT_"):
        pass
    elif prefix.startswith("UNCLASSIFIED_"):
        pass
    else:
        prefix = "BUSINESS_" + prefix
    suffix = normalized_signature.upper()
    if suffix.startswith(prefix):
        return suffix
    return f"{prefix}_{suffix}"[:96]


def _clean(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    return re.sub(r"[^a-z0-9_:/|.-]+", "", text)


def _sanitize(text: str) -> str:
    return re.sub(r"[^a-z0-9_:/|.-]+", "_", str(text).strip().lower())
