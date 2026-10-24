from __future__ import annotations

import asyncio
import json

from quentin.memory.kinds import KIND_EXPECTED_STATE_TEMPLATE, KIND_GIST_MEMORY, KIND_SITUATION_PROFILE
from quentin.memory.models import MemoryQuery, MemoryRecord, MemoryTier
from quentin.sleep.loop_impl import SleepLoop, SleepLoopConfig, SleepLoopReport


def test_emit_v3_outputs_writes_gist_and_training_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    training_pairs = tmp_path / "training_pairs.jsonl"
    skill_candidates = tmp_path / "skill_candidates.jsonl"

    cfg = SleepLoopConfig(
        training_pairs_path=str(training_pairs),
        skill_candidates_path=str(skill_candidates),
        enable_llm_consolidation=False,
        enable_consolidation_council=False,
    )
    loop = SleepLoop(config=cfg, repo_root=tmp_path)
    report = SleepLoopReport()

    records = [
        MemoryRecord.new(
            tier=MemoryTier.STS,
            source="test",
            content="tool_not_found and timeout while executing step",
            metadata={"situation_id": "ui.login", "skill_id": "skill.login.retry"},
        ),
        MemoryRecord.new(
            tier=MemoryTier.STS,
            source="test",
            content="permission denied then file not found",
            metadata={"situation_id": "ui.login", "skill_id": "skill.login.retry"},
        ),
    ]

    asyncio.run(loop._emit_v3_outputs(records, report))

    assert report.consolidated_traces == 1
    assert report.gist_memories == 1
    assert report.training_pairs == 1
    assert report.skill_candidates == 1

    gist = loop.fabric.recall(MemoryQuery(text="GIST", kind=KIND_GIST_MEMORY, mode="text_only", top_k=3))
    assert gist
    assert "GIST:" in gist[0].content

    assert training_pairs.exists()
    assert skill_candidates.exists()

    tp_line = training_pairs.read_text(encoding="utf-8").strip().splitlines()[0]
    sc_line = skill_candidates.read_text(encoding="utf-8").strip().splitlines()[0]
    tp_obj = json.loads(tp_line)
    sc_obj = json.loads(sc_line)
    assert tp_obj.get("schema_version") == "v1"
    assert sc_obj.get("schema_version") == "v1"

    profiles = loop.fabric.recall(MemoryQuery(kind=KIND_SITUATION_PROFILE, mode="text_only", top_k=10))
    assert profiles
    p0 = profiles[0]
    assert p0.metadata.get("situation_id")
    assert isinstance(p0.metadata.get("recommended_skills"), list)

    templates = loop.fabric.recall(MemoryQuery(kind=KIND_EXPECTED_STATE_TEMPLATE, mode="text_only", top_k=10))
    assert templates
    t0 = templates[0]
    assert t0.metadata.get("situation_id")
    assert isinstance(t0.metadata.get("expected_markers"), list)
