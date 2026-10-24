import json
from pathlib import Path

from meta_agent.self_programming.auditing.backlog import generate_backlog
from meta_agent.self_programming.auditing.templates import RequirementStatus, Evidence


def make_status(req_id: str, status: str, confidence: float, missing=None):
    return RequirementStatus(
        req_id=req_id,
        title=req_id,
        status=status,
        confidence=confidence,
        evidence_chain=[Evidence("ast", "symbol_missing", 0.0, "test")],
        missing_items=missing or [],
    )


def test_backlog_order_and_recommendation():
    results = [
        make_status("a", "gap", 0.1, ["missing_file:foo.py"]),
        make_status("b", "partial", 0.6, ["missing_method:Cls.fn"]),
        make_status("c", "unknown", 0.3, []),
        make_status("d", "implemented", 0.9, []),
    ]
    backlog = generate_backlog(results, top_n=3)
    items = backlog["items"]
    assert len(items) == 3
    # ensure order: gap -> unknown -> partial by status severity
    assert items[0]["req_id"] == "a"
    assert items[1]["req_id"] == "c"
    assert items[2]["req_id"] == "b"
    assert "recommendation" in items[0]
