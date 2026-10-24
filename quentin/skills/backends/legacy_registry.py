from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from quentin.skills.backends.base import SkillBackend
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.skills.registry import SkillRegistry


class LegacyRegistrySkillBackend:
    """
    Loads skills from legacy JSON registry (data/skills.json).
    """

    def __init__(self, registry_path: Path | None = None, registry_instance: Optional[SkillRegistry] = None, priority: int = 10) -> None:
        self._priority = priority
        if registry_instance:
            self._registry = registry_instance
        elif registry_path:
            self._registry = SkillRegistry(path=registry_path)
        else:
            raise ValueError("Either registry_path or registry_instance must be provided")

    @property
    def id(self) -> str:
        return "legacy_registry"

    @property
    def priority(self) -> int:
        return self._priority

    def list_skills(self, domain: str | None = None) -> List[SkillSpec]:
        items: List[SkillSpec] = []
        domain_key = str(domain or "").strip()
        
        for sk in self._registry.list_all():
            if domain_key and sk.domain not in (domain_key, "cross"):
                continue
            items.append(sk)
        return items

    def load_exec_callable(self, skill_id: str) -> Tuple[Optional[Callable[..., Any]], Optional[Any]]:
        # This backend only stores metadata for Python execution.
        # It relies on importlib to load the module.
        # We can implement basic import logic here, or assume executor handles it.
        # Given SkillBackend contract, we should try to load it if possible.
        
        spec = self._registry.get(skill_id)
        if not spec or not spec.is_implemented or not spec.is_active:
            return None, None
            
        if not spec.implementation_module or not spec.implementation_symbol:
            return None, None
            
        try:
            import importlib
            module = importlib.import_module(spec.implementation_module)
            fn = getattr(module, spec.implementation_symbol)
            return fn, spec
        except Exception:
            return None, spec

    def load_sop_text(self, skill_id: str) -> Optional[str]:
        # Legacy registry entries might have a detailed description that serves as SOP.
        spec = self._registry.get(skill_id)
        if spec and spec.detailed_description:
            return spec.detailed_description
        return None
