from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional
import json

from quentin.runtime.session_write_lock import acquire_session_write_lock


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SkillSupersedesRecord:
    old_skill_id: str
    new_skill_id: str
    approved: bool
    reason: str
    metrics_delta: Dict[str, Any] = field(default_factory=dict)
    decided_at: str = field(default_factory=_now_iso)
    approved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SupersedesStore:
    def __init__(self, *, path: str | Path = "data/skills/supersedes.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: SkillSupersedesRecord) -> None:
        lock = acquire_session_write_lock(session_file=self.path)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

