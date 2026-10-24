from __future__ import annotations

from quentin.meta.gap_extractor import extract_capability_gaps_from_exec_steps


def test_extracts_tool_not_found_gap() -> None:
    steps = [
        {
            "step_id": "s1",
            "result": {
                "status": "ok",
                "tool_result": {"status": "error", "error": "tool_not_found: tool not found: x", "tool_name": "x"},
            },
        }
    ]
    gaps = extract_capability_gaps_from_exec_steps(step_records=steps, domain="core", environment="sandbox", trace_id="t1")
    assert gaps
    assert gaps[0].gap_type == "tool_not_found"
    assert gaps[0].tool_name == "x"

