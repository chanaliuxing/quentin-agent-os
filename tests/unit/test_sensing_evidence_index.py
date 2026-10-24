from __future__ import annotations

from quentin.cognitive.loop_orchestration import build_sensing_evidence_index


def test_build_sensing_evidence_index_prefers_evidence_list() -> None:
    report = {
        "evidence": [
            {"path": "extensions/tools/xh_leads", "exists": False},
            {"path": "mutable/xh_leads.csv", "exists": True},
        ]
    }
    idx = build_sensing_evidence_index(report)
    assert idx["extensions/tools/xh_leads"]["exists"] is False
    assert idx["mutable/xh_leads.csv"]["exists"] is True


def test_build_sensing_evidence_index_supports_nested_legacy_shape() -> None:
    report = {
        "sensing_report": {
            "files": [
                {"path": "extensions/tools/xh_leads", "exists": False},
                {"path": "extensions/tools/xh_leads/logic.py", "exists": True},
            ]
        }
    }
    idx = build_sensing_evidence_index(report)
    assert idx["extensions/tools/xh_leads"]["exists"] is False
    assert idx["extensions/tools/xh_leads/logic.py"]["exists"] is True
