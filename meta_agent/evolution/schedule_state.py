# meta_agent/evolution/schedule_state.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class SelfEvolutionState:
    """
    Minimal persisted state for self-evolution scheduling and observability.

    Keep this schema stable: downstream tools (observability/coverage reports)
    depend on `load()` always returning a dict-like object with known keys.
    """

    loop_runs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SelfEvolutionState":
        if not isinstance(raw, dict):
            return cls()
        loop_runs = raw.get("loop_runs")
        if not isinstance(loop_runs, dict):
            loop_runs = {}
        last_updated_at = raw.get("last_updated_at")
        if last_updated_at is not None and not isinstance(last_updated_at, str):
            last_updated_at = None
        return cls(loop_runs=loop_runs, last_updated_at=last_updated_at)


class SelfEvolutionStateStore:
    def __init__(self, path: Path | str = Path("data/evolution/self_evolution_state.json")) -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return SelfEvolutionState().to_dict()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return SelfEvolutionState().to_dict()
        return SelfEvolutionState.from_dict(raw).to_dict()

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_state = SelfEvolutionState.from_dict(state).to_dict()
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)
