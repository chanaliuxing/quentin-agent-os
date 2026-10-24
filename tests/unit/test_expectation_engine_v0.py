from __future__ import annotations

from quentin.cognitive.perception.expectation_engine import TemplateExpectationEngine


def test_build_expected_emits_tool_success_marker() -> None:
    engine = TemplateExpectationEngine()
    out = engine.build_expected(
        situation_id="ui.login",
        tool_name="browser.click",
        step={"id": "s1"},
        ctx={},
    )
    assert out.situation_id == "ui.login"
    assert out.markers == ["tool_call_success:browser.click"]
    assert out.template_id is None
    assert out.fallback_skills == []


def test_build_expected_uses_unknown_when_situation_empty() -> None:
    engine = TemplateExpectationEngine()
    out = engine.build_expected(
        situation_id="",
        tool_name="fs.write_file",
        step={},
        ctx={},
    )
    assert out.situation_id == "unknown"


def test_compute_error_returns_none_on_success_flag() -> None:
    engine = TemplateExpectationEngine()
    expected = engine.build_expected(situation_id="s1", tool_name="t1", step={}, ctx={})
    out = engine.compute_error(expected=expected, observed={"success": True}, ctx={})
    assert out is None


def test_compute_error_returns_none_on_output_status_ok() -> None:
    engine = TemplateExpectationEngine()
    expected = engine.build_expected(situation_id="s1", tool_name="t1", step={}, ctx={})
    out = engine.compute_error(expected=expected, observed={"output": {"status": "ok"}}, ctx={})
    assert out is None


def test_compute_error_returns_prediction_error_when_failed() -> None:
    engine = TemplateExpectationEngine()
    expected = engine.build_expected(situation_id="s1", tool_name="t1", step={}, ctx={})
    out = engine.compute_error(expected=expected, observed={"success": False}, ctx={})
    assert out is not None
    assert out.error_type == "tool_call_failed"
    assert out.severity == "medium"
    assert out.missing_markers == expected.markers
    assert "hint" in out.details
