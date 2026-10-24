from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

from quentin.skills.library import SkillLibrary
from quentin.skills.schemas import SkillDefinition


async def ingest_skill_candidates(
    skill_library: SkillLibrary,
    candidates_path: str | Path = "data/training_pairs/skill_candidates.jsonl",
    domain_default: str = "cross",
    *,
    ingested_log_path: str | Path | None = None,
) -> List[str]:
    """
    Ingest skill candidates from JSONL into SkillLibrary.
    Expected fields per line:
      - candidate_id
      - title/description
      - metadata.domain (optional)
    Returns list of created skill_ids.
    """
    path = Path(candidates_path)
    if not path.exists():
        return []

    ingested_path = Path(ingested_log_path) if ingested_log_path is not None else path.with_name("skill_candidates_ingested.jsonl")
    ingested_path.parent.mkdir(parents=True, exist_ok=True)
    already: set[str] = set()
    if ingested_path.exists():
        try:
            with ingested_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        cid = str(d.get("candidate_id") or "").strip()
                        if cid:
                            already.add(cid)
                    except Exception:
                        continue
        except Exception:
            pass

    created: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj: Dict[str, Any] = json.loads(line)
            except Exception:
                continue
            candidate_id = obj.get("candidate_id")
            if candidate_id and str(candidate_id) in already:
                continue

            name = obj.get("title") or candidate_id
            desc = obj.get("description", "")
            meta = obj.get("meta") or obj.get("metadata") or {}
            domain = (meta.get("domain") if isinstance(meta, dict) else None) or domain_default
            supersedes = (meta.get("supersedes") if isinstance(meta, dict) else None)

            steps = obj.get("steps") or []
            plan_steps = None
            if isinstance(steps, list) and steps:
                plan_steps = [
                    {"description": s, "tool": "noop", "params": {"source": "skill_candidate"}}
                    for s in steps
                    if isinstance(s, str) and s.strip()
                ] or None
            skill = await skill_library.register_skill(
                name=name,
                kind="procedural",
                description=desc,
                domain=domain,
                tags=["sleep_loop", "candidate"],
                supersedes=supersedes,
                plan_steps=plan_steps,
                meta={
                    **(meta if isinstance(meta, dict) else {}),
                    "candidate_id": candidate_id,
                    "schema_version": obj.get("schema_version"),
                    "evaluation_status": (meta.get("evaluation_status") if isinstance(meta, dict) else None) or "candidate",
                },
            )
            created.append(skill.skill_id)
            if candidate_id:
                try:
                    with ingested_path.open("a", encoding="utf-8") as lf:
                        lf.write(
                            json.dumps(
                                {"candidate_id": candidate_id, "skill_id": skill.skill_id},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                except Exception:
                    pass
    return created
