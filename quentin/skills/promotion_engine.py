from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Dict, Any
from quentin.skills.candidate_pipeline import SkillCandidate, SkillCandidateStore
from quentin.skills.validator import SkillValidator
from quentin.skills.registry import FileBackedSkillRegistry
from quentin.skills.schema import SkillSpec, SkillStatus

logger = logging.getLogger(__name__)

class SkillPromotionEngine:
    """
    P5: Ported from OpenClaw's skill promotion pipeline.
    Orchestrates the lifecycle from SkillCandidate to Active Skill.
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.validator = SkillValidator(repo_root)
        self.registry = FileBackedSkillRegistry(path=repo_root / "data" / "skills.json")
        self.candidate_store = SkillCandidateStore(path=repo_root / "data" / "skill_candidates.jsonl")

    async def process_pending_candidates(self) -> int:
        """
        Scans candidate store and attempts to promote them.
        """
        candidates = self.candidate_store.list_all()
        promoted_count = 0
        
        for cand in candidates:
            if cand.meta.get("status") == "verified":
                continue
                
            # 1. Physical Validation
            success, logs = self.validator.validate_candidate(cand)
            
            if success:
                # 2. Atomic Promotion (OpenClaw Parity)
                self._promote_to_active(cand)
                cand.meta["status"] = "verified"
                # Update candidate store state
                promoted_count += 1
            else:
                cand.meta["status"] = "failed_validation"
                cand.meta["last_error"] = logs
                
        return promoted_count

    def _promote_to_active(self, cand: SkillCandidate):
        """
        Physically registers the skill and persists the code.
        """
        # Save Python implementation to library
        lib_dir = self.repo_root / "quentin" / "skills" / "library"
        lib_dir.mkdir(parents=True, exist_ok=True)
        
        code_path = lib_dir / f"{cand.name}.py"
        code_path.write_text(cand.implementation_code, encoding="utf-8")
        
        # Register in JSON Registry
        spec = SkillSpec(
            id=cand.candidate_id,
            name=cand.name,
            domain=cand.domain,
            short_description=cand.scope.get("description", ""),
            detailed_description=cand.scope.get("description", ""),
            status=SkillStatus.ACTIVE,
            tags=cand.meta.get("tags", []),
            notes=f"auto_promoted_from_task_{cand.meta.get('from_task_id')}"
        )
        self.registry.register(spec)
        
        # 3. Event Broadcast (OpenClaw Parity)
        try:
            from quentin.infra.events.environment_bus import environment_bus
            environment_bus.emit("skill_activated", {"skill_id": spec.id, "name": spec.name})
        except Exception: pass
        
        logger.info(f"PromotionEngine: Skill '{cand.name}' is now ACTIVE.")
