from __future__ import annotations

from dataclasses import dataclass

from quentin.cognitive.loop import CognitiveTask, CognitiveResult
from quentin.goals.done_definition import DoneCheckResult
from quentin.skills.miner import SkillMiner
from quentin.skills.candidate_pipeline import SkillCandidateStore


@dataclass
class _StubDecision:
    final_answer: str


class _StubCouncil:
    def deliberate(self, *, question: str, context: str, mode: str):
        return _StubDecision(
            final_answer=(
                "NAME:\nExtractFoo\n"
                "DOMAIN:\ncore\n"
                "DESCRIPTION:\nDo foo.\n"
                "CODE:\nprint('foo')\n"
                "TESTS:\ndef test_candidate_smoke():\n    assert True\n"
                "QUALITY_NOTES:\nworks on toy input\n"
            )
        )


def test_skill_miner_writes_candidate_for_done_task(tmp_path):
    store = SkillCandidateStore(path=tmp_path / "candidates.jsonl")
    miner = SkillMiner(council=_StubCouncil(), candidate_store=store)

    task = CognitiveTask(input_text="x", task_id="t1", domain="core")
    result = CognitiveResult(
        task_id="t1",
        goal_id="g1",
        final_output="ok",
        plan_summary="",
        actions_summary="",
        done_result=DoneCheckResult(is_done=True, confidence=1.0),
        done=True,
        done_confidence=1.0,
    )

    cand = miner.mine_from_task(task=task, result=result, trace_events=[])
    assert cand is not None
    assert cand.domain == "core"
    assert "ExtractFoo" in cand.name
