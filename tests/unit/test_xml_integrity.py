from __future__ import annotations

from quentin.cognitive.xml_integrity import repair_unclosed_xml_tags, repair_structured_response
from quentin.cognitive.attempt_response_parser import parse_model_response_text


def test_repair_unclosed_xml_tags_closes_missing_final() -> None:
    text = "<think>analysis</think><final>{\"steps\": []}"
    out = repair_unclosed_xml_tags(text)
    assert out.endswith("</final>")


def test_parse_model_response_text_handles_truncated_final_tag() -> None:
    text = "<think>plan</think><final>done output"
    parsed = parse_model_response_text(text)
    assert parsed.final == "done output"
    assert parsed.has_structured_tags is True


def test_repair_structured_response_fixes_malformed_nesting() -> None:
    text = "<think>t<final>{\"k\":1}</think>"
    repaired, report = repair_structured_response(text)
    assert "</final>" in repaired
    assert bool(report.get("malformed_nesting_fixed", False)) is True
    assert bool(report.get("applied", False)) is True


def test_repair_structured_response_trims_dangling_tag_head() -> None:
    text = "<final>{\"a\":1}</final><thin"
    repaired, report = repair_structured_response(text)
    assert repaired.endswith("</final>")
    assert bool(report.get("dangling_head_trimmed", False)) is True
