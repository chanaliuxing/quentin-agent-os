# quentin/skills/task_builder.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# Adapt to EngineV2's expected input interface
@dataclass
class ProgrammingTask:
    id: str
    title: str
    description: str
    category: str = "skill_implementation"
    priority: int = 1
    related_files: List[str] = None # Usually empty for new skill
    domain: Optional[str] = None
    target_file: Optional[str] = None

class SkillTaskBuilder:
    def __init__(self, skills_dir: str = "quentin/mutable/skills"):
        self.skills_dir = skills_dir

    def build_task(self, candidate: Dict[str, Any]) -> ProgrammingTask:
        cid = candidate.get("candidate_id", "unknown")
        name = candidate.get("skill_name") or candidate.get("title", f"skill_{cid}")
        # Normalize name
        name = name.lower().replace(" ", "_").replace("-", "_")
        
        target_file = f"{self.skills_dir}/{name}.py"
        
        desc = self._build_description(candidate, target_file, name)
        
        return ProgrammingTask(
            id=cid,
            title=f"Implement New Skill: {name}",
            description=desc,
            category="new_feature",
            priority=candidate.get("priority", 2),
            related_files=[], # Empty implies "create new" or "no context needed"
            domain=candidate.get("metadata", {}).get("domain", "core"),
            target_file=target_file
        )

    def _build_description(self, c: Dict[str, Any], target_file: str, name: str) -> str:
        prompt = [
            f"GOAL: Create a new reusable python skill '{name}' in the file `{target_file}`.",
            "",
            "DESCRIPTION:",
            c.get("description", "No description provided."),
            "",
            "REQUIREMENTS:",
            "1. The file must contain a main function/class matching the skill name.",
            "2. Include docstrings and type hints.",
            "3. No external dependencies outside standard library unless specified.",
            f"4. The implementation MUST be verifiable by a test.",
        ]
        
        # Add examples if available (Critical for success)
        examples = c.get("examples", [])
        if c.get("source_record_ids"): 
            # Phase 2 might pass raw source IDs, Phase 3 miner should hydrate them.
            # Here we assume examples are ready or we rely on description.
            pass

        if examples:
            prompt.append("\nEXAMPLES/TEST CASES:")
            for idx, ex in enumerate(examples):
                prompt.append(f"Case {idx+1}: Input={ex.get('input')} -> Output={ex.get('output')}")
                
        constraints = c.get("constraints", {})
        if constraints:
            prompt.append("\nCONSTRAINTS:")
            for k, v in constraints.items():
                prompt.append(f"- {k}: {v}")

        return "\n".join(prompt)
