from __future__ import annotations

from quentin.council.done import DoneCouncil
from quentin.council.manager import CouncilDecision, CouncilMemberReply


class _StubCouncilManager:
    def __init__(self, finals):
        self._finals = list(finals)
        self.calls = 0

    def run_council(self, council_name, question):  # type: ignore[no-untyped-def]
        _ = (council_name, question)
        self.calls += 1
        final = self._finals[min(self.calls - 1, len(self._finals) - 1)]
        return CouncilDecision(
            council_name="done",
            topic="done_check",
            final=final,
            member_replies=[CouncilMemberReply(member_id="m1", raw_output="", parsed=final, error=None)],
            arbiter_raw=None,
            created_at="2026-02-10T00:00:00+00:00",
        )


def test_done_council_retries_when_reasoning_is_weak() -> None:
    cm = _StubCouncilManager(
        finals=[
            {"verdict": "continue", "reasoning": "no reasoning"},
            {"verdict": "continue", "reasoning": "verification command failed: python -m py_compile"},
        ]
    )
    council = DoneCouncil(council_manager=cm)
    decision = council.assess(
        goal={"id": "g1", "title": "Fix parser"},
        execution_summary={"final_output": "", "actions_summary": "compile failed"},
        metrics={"error_rate": 1.0},
    )
    assert cm.calls == 2
    assert decision.is_done is False
    assert "no reasoning" not in decision.reason.lower()


def test_done_council_uses_evidence_fallback_when_reasoning_stays_weak() -> None:
    cm = _StubCouncilManager(
        finals=[
            {"verdict": "continue", "reasoning": "no reasoning"},
            {"verdict": "continue", "reasoning": "n/a"},
        ]
    )
    council = DoneCouncil(council_manager=cm)
    decision = council.assess(
        goal={"id": "g1", "title": "Fix parser"},
        execution_summary={"final_output": "error: import failed", "actions_summary": ""},
        metrics={"error_rate": 1.0},
    )
    assert cm.calls == 2
    assert decision.is_done is False
    assert "council_quality_fallback" in decision.reason
