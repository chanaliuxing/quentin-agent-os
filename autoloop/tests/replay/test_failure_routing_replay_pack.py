import json
from pathlib import Path

import pytest

from app.control import route_recovery_action


def _load_replay_pack() -> list[dict]:
    pack_file = Path(__file__).parent / "data" / "failure_routing_pack.json"
    return json.loads(pack_file.read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", _load_replay_pack(), ids=lambda item: str(item.get("name", "case")))
def test_failure_routing_replay_pack(sample: dict):
    payload = dict(sample["input"])
    action = route_recovery_action(
        status=payload["status"],
        acceptance_status=payload["acceptance_status"],
        failed_modules=list(payload.get("failed_modules", [])),
        replan_rounds=int(payload.get("replan_rounds", 0)),
        reviewer_codes=list(payload.get("reviewer_codes", [])),
        failure_type=str(payload.get("failure_type", "")),
        first_failure_stage=str(payload.get("first_failure_stage", "")),
        failure_signature_count=int(payload.get("failure_signature_count", 0)),
        max_review_loops=int(payload.get("max_review_loops", 2)),
    )
    assert action == sample["expected_action"]
