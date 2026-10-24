# quentin/skills/store.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import logging

from quentin.skills.schema import (
    SkillDefinition,
    SkillCandidate,
    SkillSupersedesRecord,
)

logger = logging.getLogger(__name__)
from quentin.runtime.session_write_lock import acquire_session_write_lock


class SkillStore:
    """
    v1: 基于文件系统的 Skill 存储。
    将来可替换为 DB / 对象存储。

    目录结构：
    - data/skills/definitions/{skill_id}.json
    - data/skills/candidates/{candidate_id}.json
    - data/skills/supersedes.jsonl
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "skills"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.def_dir = self.base_dir / "definitions"
        self.def_dir.mkdir(parents=True, exist_ok=True)

        self.cand_dir = self.base_dir / "candidates"
        self.cand_dir.mkdir(parents=True, exist_ok=True)

        self.supersedes_path = self.base_dir / "supersedes.jsonl"

    # -------- SkillDefinition -------- #
    def save_skill(self, skill: SkillDefinition) -> None:
        path = self.def_dir / f"{skill.skill_id}.json"
        try:
            path.write_text(
                json.dumps(skill.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("SkillStore: failed to save skill %s", path)

    def load_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        path = self.def_dir / f"{skill_id}.json"
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            from quentin.skills.schema import SkillDefinition, SkillStats, SkillTestCase

            stats = SkillStats(**obj.get("performance_stats", {{}}))
            test_cases = [SkillTestCase(**tc) for tc in obj.get("test_cases", [])]
            return SkillDefinition(
                skill_id=obj["skill_id"],
                name=obj.get("name", ""),
                version=int(obj.get("version", 1)),
                description=obj.get("description", ""),
                domain=obj.get("domain", "general"),
                entry_point=obj.get("entry_point", ""),
                tags=obj.get("tags", []),
                created_at=obj.get("created_at", ""),
                created_by=obj.get("created_by", "system"),
                safety_level=obj.get("safety_level", "medium"),
                status=obj.get("status", "active"),
                supersedes=obj.get("supersedes"),
                superseded_by=obj.get("superseded_by"),
                test_cases=test_cases,
                performance_stats=stats,
                meta=obj.get("meta", {{}})
            )
        except Exception:
            logger.exception("SkillStore: failed to load skill %s", path)
            return None

    def list_skills(self) -> List[SkillDefinition]:
        skills: List[SkillDefinition] = []
        for path in self.def_dir.glob("*.json"):
            s = self.load_skill(path.stem)
            if s is not None:
                skills.append(s)
        return skills

    # -------- SkillCandidate -------- #
    def save_candidate(self, cand: SkillCandidate) -> None:
        path = self.cand_dir / f"{cand.candidate_id}.json"
        try:
            path.write_text(
                json.dumps(cand.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("SkillStore: failed to save candidate %s", path)

    def load_candidate(self, candidate_id: str) -> Optional[SkillCandidate]:
        path = self.cand_dir / f"{candidate_id}.json"
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            from quentin.skills.schema import SkillDefinition

            sd = SkillDefinition(**obj["proposed_skill"])
            return SkillCandidate(
                candidate_id=obj["candidate_id"],
                base_skill_id=obj.get("base_skill_id"),
                proposed_skill=sd,
                origin=obj.get("origin", {{}}),
                status=obj.get("status", "pending_eval"),
                created_at=obj.get("created_at", ""),
                created_by=obj.get("created_by", "self_programming_engine"),
                notes=obj.get("notes", ""),
            )
        except Exception:
            logger.exception("SkillStore: failed to load candidate %s", path)
            return None

    def list_candidates(self, status: Optional[str] = None, limit: int = 100) -> List[SkillCandidate]:
        cands: List[SkillCandidate] = []
        for path in self.cand_dir.glob("*.json"):
            c = self.load_candidate(path.stem)
            if c is None:
                continue
            if status is not None and c.status != status:
                continue
            cands.append(c)
            if len(cands) >= limit:
                break
        return cands

    # -------- Supersedes -------- #
    def append_supersedes_record(self, rec: SkillSupersedesRecord) -> None:
        line = json.dumps(rec.to_dict(), ensure_ascii=False)
        try:
            lock = acquire_session_write_lock(session_file=self.supersedes_path)
            try:
                with self.supersedes_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("SkillStore: failed to append supersedes record to %s", self.supersedes_path)
