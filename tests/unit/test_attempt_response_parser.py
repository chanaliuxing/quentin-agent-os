from __future__ import annotations

from quentin.cognitive.attempt_response_parser import parse_model_response_text, detect_repetition


def test_parse_model_response_text_extracts_think_and_final() -> None:
    text = "<think>plan first</think>\n<final>done output</final>"
    out = parse_model_response_text(text)
    assert out.has_structured_tags is True
    assert out.think == "plan first"
    assert out.final == "done output"
    assert out.xml_repair_mode in {"none", "xml_tag_balance"}


def test_parse_model_response_text_uses_fenced_fallback() -> None:
    text = "```json\n{\"steps\": []}\n```"
    out = parse_model_response_text(text)
    assert "{\"steps\": []}" in out.final


def test_detect_repetition_true_for_repeated_lines() -> None:
    text = "same line\nsame line\nsame line\nsame line"
    assert detect_repetition(text) is True
