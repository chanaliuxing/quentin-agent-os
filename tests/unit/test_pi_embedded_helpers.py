from __future__ import annotations

from quentin.agents.pi_embedded_helpers.errors import classify_error_taxonomy
from quentin.agents.pi_embedded_helpers.json_truncation import truncate_json_obj
from quentin.agents.pi_embedded_helpers.repetition_detection import detect_repetitive_sequence
from quentin.agents.pi_embedded_helpers.xml import enforce_closed_tag_blocks


def test_error_taxonomy_maps_context_overflow() -> None:
    tax = classify_error_taxonomy("maximum context length exceeded")
    assert tax.kind == "context_overflow"
    assert tax.retryable is True
    assert tax.reflection_weight in {"high", "critical"}


def test_repetition_detection_finds_repeated_signature() -> None:
    sig = detect_repetitive_sequence(["a", "a", "a"], window=3)
    assert sig == "a"


def test_xml_helper_closes_unclosed_tags() -> None:
    text = "<final>{\"status\":\"ok\"}"
    fixed = enforce_closed_tag_blocks(text, tags=("final",))
    assert fixed.endswith("</final>")


def test_json_truncation_handles_large_object() -> None:
    payload = {"items": [{"id": i, "v": "x" * 40} for i in range(100)]}
    out = truncate_json_obj(payload, max_chars=500)
    assert len(out) > 0
    assert "items" in out

