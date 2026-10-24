import asyncio
import json
from pathlib import Path

import pytest

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery
from quentin.memory.sleep_loop import SleepLoop, SleepLoopConfig
from quentin.traces.core import JsonlTraceRecorder


class StubCouncil:
    async def ask_text(self, role: str, question: str, context):
        return "summary of traces"


@pytest.mark.asyncio
async def test_sleep_loop_consolidation_writes_outputs(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    training_pairs_path = tmp_path / "training_pairs.jsonl"
    skill_candidates_path = tmp_path / "skill_candidates.jsonl"

    fabric = MemoryFabric(db_path=db_path, use_postgres=False)
    # seed STS records that look like traces
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="trace content",
        source="execution_trace",
        metadata={"tags": ["trace"], "domain": "test"},
    )
    fabric.store.add(rec)

    cfg = SleepLoopConfig(
        max_records_per_run=20,
        training_pairs_path=str(training_pairs_path),
        skill_candidates_path=str(skill_candidates_path),
    )
    recorder = JsonlTraceRecorder(repo_root=tmp_path)
    loop = SleepLoop(
        memory_fabric=fabric,
        config=cfg,
        council=StubCouncil(),
        trace_recorder=recorder,
    )

    report = await loop.run_once()

    # summary should be written as MTS or LTS record
    mts_records = fabric.recall(MemoryQuery(tier=MemoryTier.MTS, text="summary"))
    lts_records = fabric.recall(MemoryQuery(tier=MemoryTier.LTS, text="summary"))
    assert mts_records or lts_records

    # training pairs and skill candidates should be written
    assert training_pairs_path.exists()
    assert skill_candidates_path.exists()
    assert training_pairs_path.read_text(encoding="utf-8").strip()
    assert skill_candidates_path.read_text(encoding="utf-8").strip()
    # schema version should be present in v3 outputs
    tp_obj = json.loads(training_pairs_path.read_text(encoding="utf-8").splitlines()[-1])
    sc_obj = json.loads(skill_candidates_path.read_text(encoding="utf-8").splitlines()[-1])
    assert tp_obj.get("schema_version") == "v1"
    assert sc_obj.get("schema_version") == "v1"

    # report counts should reflect outputs
    assert report.consolidated_traces >= 1
    assert report.training_pairs >= 1
    assert report.skill_candidates >= 1
