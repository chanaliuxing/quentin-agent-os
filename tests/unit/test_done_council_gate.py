from __future__ import annotations

from quentin.council.done import DoneCouncil


def test_done_council_can_be_disabled_with_heuristic_accept(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_ENABLED", "0")
    dc = DoneCouncil(council_manager=None)

    decision = dc.assess(
        goal={"id": "g1"},
        execution_summary={"actions_summary": "fs.read_file: AGENTS.md; fs.write_file: generated/report.txt"},
        metrics={"total_attempts": 1},
    )

    assert decision.is_done is True
    assert decision.verdict == "done"
    assert "heuristic execution evidence" in decision.reason


def test_done_council_disabled_heuristic_rejects_failure_summary(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_ENABLED", "0")
    dc = DoneCouncil(council_manager=None)

    decision = dc.assess(
        goal={"id": "g1"},
        execution_summary={"final_output": "timeout while writing artifact"},
        metrics={"total_attempts": 1},
    )

    assert decision.is_done is False
    assert decision.verdict == "not_done"
