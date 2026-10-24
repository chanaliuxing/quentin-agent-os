import json
from pathlib import Path

import pytest

from app.metrics.business_failure_signature_normalizer import (
    infer_taxonomy_candidate_name,
    normalize_business_failure_signature,
)


def _load_goldens() -> list[dict]:
    root = Path(__file__).parent / "business_failure_golden_pack"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]


@pytest.mark.parametrize("sample", _load_goldens())
def test_business_failure_golden_pack(sample: dict):
    signature = normalize_business_failure_signature(
        primary_failure_type=str(sample.get("primary_failure_type", "")),
        first_failure_stage=str(sample.get("first_failure_stage", "")),
        missing_artifacts=[str(item) for item in sample.get("missing_artifacts", []) if str(item).strip()],
        grader_results={str(k): str(v) for k, v in dict(sample.get("grader_results", {}) or {}).items()},
        failure_events=[item for item in sample.get("failure_events", []) if isinstance(item, dict)],
    )
    candidate = infer_taxonomy_candidate_name(
        signature=signature,
        primary_failure_type=str(sample.get("primary_failure_type", "")),
    )
    assert signature == str(sample.get("expected_signature", "")).strip().lower()
    assert candidate == str(sample.get("expected_candidate_enum", "")).strip().upper()
