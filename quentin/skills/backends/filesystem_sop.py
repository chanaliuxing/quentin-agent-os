from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from quentin.skills.backends.base import SkillBackend
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.skills.sop_plugin_loader import discover_sop_skills, load_sop_skill_md


class FileSystemSOPSkillBackend:
    """
    Loads SOP skills from filesystem markdown (docs/skills/*.md).
    """

    def __init__(self, repo_root: Path, priority: int = 50) -> None:
        self.repo_root = repo_root
        self._priority = priority

    @property
    def id(self) -> str:
        return "filesystem_sop"

    @property
    def priority(self) -> int:
        return self._priority

    def list_skills(self, domain: str | None = None) -> List[SkillSpec]:
        """
        Discover markdown files and convert to lightweight SkillSpecs.
        Includes structured SOP skills and flat markdown prompts.
        """
        items: List[SkillSpec] = []
        key = str(domain or "").strip()
        seen_ids = set()
        
        # 1. Structured SOP skills (directories with SKILL.md)
        for sk in discover_sop_skills(self.repo_root):
            skill_domain = str(sk.meta.get("domain") or "core")
            if key and skill_domain not in (key, "cross"):
                continue

            spec = SkillSpec(
                id=sk.skill_id,
                name=sk.name,
                domain=skill_domain,
                short_description=sk.description or "",
                detailed_description=sk.description or "",
                status=SkillStatus.ACTIVE,
                tags=list(sk.meta.get("tags") or []) + list(sk.triggers or []),
                implementation_module=None,
                implementation_symbol=None,
                is_implemented=False,
                is_active=True,
                notes=f"filesystem_sop:{sk.skill_md_path}",
                metadata=dict(sk.meta or {}),
            )
            items.append(spec)
            seen_ids.add(spec.id)

        # 2. Flat markdown skills (quentin/mutable/skills/*.md)
        flat_dir = self.repo_root / "quentin" / "mutable" / "skills"
        if flat_dir.exists():
            for p in sorted(flat_dir.glob("*.md")):
                stem = p.stem.strip()
                if not stem or stem in seen_ids:
                    continue
                # Simple heuristic for flat files: domain usually not encoded, assume core or from filename
                # e.g. "planning_v1.md"
                
                # Check domain filter if simple prefix match
                if key and not stem.startswith(key):
                    # Loose check, accept if key is empty or matches prefix
                    pass 
                
                # Create a minimal spec
                spec = SkillSpec(
                    id=stem,
                    name=stem,
                    domain="core", # Default
                    short_description=f"Flat markdown skill: {stem}",
                    detailed_description="",
                    status=SkillStatus.ACTIVE,
                    tags=[],
                    implementation_module=None,
                    implementation_symbol=None,
                    is_implemented=False,
                    is_active=True,
                    notes=f"filesystem_sop_flat:{p}",
                    metadata={"path": str(p)},
                )
                items.append(spec)
                seen_ids.add(stem)

        return items

    def load_exec_callable(self, skill_id: str) -> Tuple[Optional[Callable[..., Any]], Optional[Any]]:
        # SOP skills are text-only prompts, not python callables.
        return None, None

    def load_sop_text(self, skill_id: str) -> Optional[str]:
        # 1. Try flat file first (fastest, common case for mutable skills)
        cleaned = str(skill_id or "").strip()
        if not cleaned:
            return None
            
        flat_path = self.repo_root / "quentin" / "mutable" / "skills" / f"{cleaned}.md"
        if flat_path.exists():
            try:
                return flat_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # 2. Try structured SOP lookup
        try:
            return load_sop_skill_md(repo_root=self.repo_root, skill_id=skill_id)
        except Exception:
            return None
