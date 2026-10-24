import json
from pathlib import Path

from meta_agent.self_programming.auditing.task_builder import RemediationTaskBuilder
from meta_agent.self_programming.auditing.templates import RequirementStatus, Evidence


def make_req(req_id: str, status: str, missing=None, evidences=None, confidence=0.3):
    return RequirementStatus(
        req_id=req_id,
        title=req_id,
        status=status,
        confidence=confidence,
        evidence_chain=evidences or [],
        missing_items=missing or [],
    )


def test_task_builder_prioritizes_regressions_and_gaps():
    reg = {"id": "imp1", "from": "implemented", "to": "gap", "confidence_delta": -0.5}
    results = [
        make_req("imp1", "gap"),
        make_req("b", "partial"),
        make_req("a", "unknown"),
    ]
    tasks = RemediationTaskBuilder(max_tasks=3).build(results, delta={"status_changed": [reg]})
    ids = [t["req_id"] for t in tasks["tasks"]]
    assert ids[0] == "imp1"


def test_task_builder_types():
    r1 = make_req("missing_file", "gap", missing=["missing_file:foo.py"])
    r2 = make_req("missing_method", "gap", missing=["missing_method:Cls.fn"])
    r3 = make_req("placeholder", "partial", evidences=[Evidence("ast", "placeholder_detected", -0.3, "")])
    tasks = RemediationTaskBuilder(max_tasks=3).build([r1, r2, r3], delta=None)["tasks"]
    tmap = {t["req_id"]: t["task_type"] for t in tasks}
    assert tmap["missing_file"] == "FIX_MODULE_HINT"
    assert tmap["missing_method"] == "ADD_SYMBOL_STUB"
    assert tmap["placeholder"] == "REPLACE_PLACEHOLDER"
