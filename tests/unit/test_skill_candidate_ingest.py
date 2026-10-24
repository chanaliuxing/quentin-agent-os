import asyncio
import json
from pathlib import Path

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore, KVStoreConfig
from quentin.skills.ingest import ingest_skill_candidates
from quentin.skills.library import SkillLibrary


def test_ingest_skill_candidates_creates_skills(tmp_path: Path) -> None:
    candidates_path = tmp_path / "data" / "training_pairs" / "skill_candidates.jsonl"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "candidate_id": "c1",
                "title": "Do thing",
                "steps": ["step 1", "step 2"],
                "meta": {"domain": "cross"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    kv = KVStore(config=KVStoreConfig(db_path=str(tmp_path / "kv.sqlite3")))
    tracer = Tracer(store=kv)
    lib = SkillLibrary(tracer=tracer, kv=kv)

    created = asyncio.run(ingest_skill_candidates(lib, candidates_path=candidates_path))
    assert len(created) == 1

    skill = asyncio.run(lib.get_skill(created[0]))
    assert skill is not None
    assert skill.name == "Do thing"
    assert skill.plan_steps is not None
    assert len(skill.plan_steps) >= 2
    assert (skill.meta or {}).get("candidate_id") == "c1"

