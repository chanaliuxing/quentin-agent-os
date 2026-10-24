# tests/unit/test_done_council_protocol_compat.py
import pytest
from quentin.council.done import DoneCouncil, CouncilDecision

def test_done_council_protocol_compat():
    # Case 1: is_done = True
    final1 = {"verdict": "done", "is_done": True, "reasoning": "Completed everything."}
    v1, ok1 = DoneCouncil._resolve_done_from_final(final1)
    assert v1 == "done"
    assert ok1 is True

    # Case 2: done = "true" (string)
    final2 = {"verdict": "complete", "done": "true", "reasoning": "Done."}
    v2, ok2 = DoneCouncil._resolve_done_from_final(final2)
    assert v2 == "done"
    assert ok2 is True

    # Case 3: done = "1" (string)
    final3 = {"done": "1"}
    v3, ok3 = DoneCouncil._resolve_done_from_final(final3)
    assert v3 == "done"
    assert ok3 is True

    # Case 4: verdict = "not_done"
    final4 = {"verdict": "not_done", "is_done": False}
    v4, ok4 = DoneCouncil._resolve_done_from_final(final4)
    assert v4 == "not_done"
    assert ok4 is False

    # Case 5: ambiguous but is_done wins
    final5 = {"verdict": "undecided", "is_done": False}
    v5, ok5 = DoneCouncil._resolve_done_from_final(final5)
    assert v5 == "not_done"
    assert ok5 is False

    # Case 6: verdict with 'complete'
    final6 = {"verdict": "it is complete"}
    v6, ok6 = DoneCouncil._resolve_done_from_final(final6)
    assert v6 == "done"
    assert ok6 is True
