from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json

from .schema import SkillSpec, SkillStatus
from quentin.utils.time import now_utc, normalize_to_utc_iso


class SkillRegistry:
    """
    v1: 简单 JSON 文件存储所有 SkillSpec。
    后面可以换成 DB 或者走 Patch/Codegen 流程。
    """

    def __init__(self, path: str | Path = "data/skills.json"):
        self.path = Path(path)
        self._skills: Dict[str, SkillSpec] = {}
        self._loaded = False

    # ---- internal ----

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            for item in raw:
                spec = self._from_dict(item)
                self._skills[spec.id] = spec
        self._loaded = True

    def _flush(self) -> None:
        payload = [self._to_dict(s) for s in self._skills.values()]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _to_dict(self, spec: SkillSpec) -> dict:
        return {
            "id": spec.id,
            "name": spec.name,
            "domain": spec.domain,
            "short_description": spec.short_description,
            "detailed_description": spec.detailed_description,
            "created_at": spec.created_at.isoformat(),
            "updated_at": spec.updated_at.isoformat(),
            "created_by": spec.created_by,
            "version": spec.version,
            "status": spec.status.value,
            "tags": spec.tags,
            "parameters": spec.parameters,
            "examples": [
                {
                    "input": e.input,
                    "output": e.output,
                    "notes": e.notes,
                }
                for e in spec.examples
            ],
            "impl_stub_path": spec.impl_stub_path,
            "source_trace_ids": spec.source_trace_ids,
            "notes": spec.notes,
        }

    def _from_dict(self, d: dict) -> SkillSpec:
        from .schema import SkillExample
        spec = SkillSpec(
            id=d["id"],
            name=d["name"],
            domain=d["domain"],
            short_description=d["short_description"],
            detailed_description=d["detailed_description"],
            created_at=datetime.fromisoformat(normalize_to_utc_iso(d["created_at"])),
            updated_at=datetime.fromisoformat(normalize_to_utc_iso(d["updated_at"])),
            created_by=d.get("created_by", "skill_evolution_loop"),
            version=d.get("version", "0.1.0"),
            status=SkillStatus(d.get("status", SkillStatus.DRAFT.value)),
            tags=d.get("tags", []),
            parameters=d.get("parameters", {}),
            examples=[SkillExample(**e) for e in d.get("examples", [])],
            impl_stub_path=d.get("impl_stub_path"),
            source_trace_ids=d.get("source_trace_ids", []),
            notes=d.get("notes", ""),
        )
        return spec

    # ---- public APIs ----

    def list_skills(
        self,
        domain: Optional[str] = None,
        status: Optional[SkillStatus] = None,
        tag: Optional[str] = None,
    ) -> List[SkillSpec]:
        self._ensure_loaded()
        values = list(self._skills.values())
        if domain:
            values = [s for s in values if s.domain == domain or s.domain == "cross"]
        if status:
            values = [s for s in values if s.status == status]
        if tag:
            values = [s for s in values if tag in s.tags]
        return sorted(values, key=lambda s: s.created_at)

    def get(self, skill_id: str) -> Optional[SkillSpec]:
        self._ensure_loaded()
        return self._skills.get(skill_id)

    def register(self, spec: SkillSpec) -> SkillSpec:
        self._ensure_loaded()
        self._skills[spec.id] = spec
        self._flush()
        return spec

    def update_status(self, skill_id: str, status: SkillStatus) -> None:
        self._ensure_loaded()
        spec = self._skills.get(skill_id)
        if not spec:
            return
        spec.status = status
        spec.updated_at = now_utc()
        self._flush()

FileBackedSkillRegistry = SkillRegistry
