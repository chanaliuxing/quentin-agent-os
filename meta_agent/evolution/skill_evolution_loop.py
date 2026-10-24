from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import warnings

from quentin.skills.candidate_pipeline import SkillCandidateStore


@dataclass
class SkillEvolutionConfig:
    max_lessons: int = 30
    max_skills_per_cycle: int = 10


class SkillEvolutionLoop:
    """
    Compatibility shim for legacy `meta_agent.evolution.skill_evolution_loop`.

    Canonical skill evolution path in Quentin uses:
    - `quentin.skills.miner.SkillMiner`
    - `quentin.skills.candidate_pipeline.SkillCandidateStore`
    """

    def __init__(
        self,
        memory_store: Any = None,
        skill_registry: Any = None,
        config: Optional[SkillEvolutionConfig] = None,
    ) -> None:
        self.memory_store = memory_store
        self.skill_registry = skill_registry
        self.config = config or SkillEvolutionConfig()
        self._candidate_store = SkillCandidateStore()
        warnings.warn(
            "meta_agent.evolution.skill_evolution_loop.SkillEvolutionLoop is deprecated; "
            "use quentin.skills.* pipeline instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def run(self) -> Dict[str, Any]:
        # Legacy loop intentionally does not auto-generate skills anymore to avoid split-brain behavior.
        # It only reports pending candidates discovered by Quentin's canonical pipeline.
        pending = self._candidate_store.load_all(limit=max(1, int(self.config.max_skills_per_cycle)))
        return {
            "status": "deprecated_shim",
            "pending_skill_candidates": len(pending),
            "max_skills_per_cycle": int(self.config.max_skills_per_cycle),
        }

