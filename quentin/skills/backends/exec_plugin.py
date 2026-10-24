from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from quentin.skills.backends.base import SkillBackend
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.skills.exec_plugin_loader import discover_exec_skill_plugins, load_exec_skill_callable, resolve_exec_skill


class ExecPluginSkillBackend:
    """
    Loads executable skills from plugins (extensions/skills/*.py).
    """

    def __init__(self, repo_root: Path, priority: int = 100) -> None:
        self.repo_root = repo_root
        self._priority = priority

    @property
    def id(self) -> str:
        return "exec_plugin"

    @property
    def priority(self) -> int:
        return self._priority

    def list_skills(self, domain: str | None = None) -> List[SkillSpec]:
        items: List[SkillSpec] = []
        domain_key = str(domain or "").strip()
        
        for sk in discover_exec_skill_plugins(self.repo_root):
            if domain_key and sk.domain not in (domain_key, "cross"):
                continue
            
            spec = SkillSpec(
                id=sk.skill_id,
                name=sk.name,
                domain=sk.domain,
                short_description=sk.description or "",
                detailed_description=sk.description or "",
                status=SkillStatus.ACTIVE,
                tags=list(sk.tags or []),
                implementation_module=sk.plugin_path, # Path to plugin file or module
                implementation_symbol=sk.entrypoint,
                is_implemented=True,
                is_active=True,
                notes=f"exec_plugin:{sk.plugin_path}",
                metadata=dict(sk.meta or {}),
            )
            items.append(spec)
        return items

    def load_exec_callable(self, skill_id: str) -> Tuple[Optional[Callable[..., Any]], Optional[Any]]:
        plugin = resolve_exec_skill(self.repo_root, skill_id)
        if plugin is None:
            return None, None
        try:
            fn = load_exec_skill_callable(plugin=plugin)
            return fn, plugin
        except Exception:
            return None, plugin

    def load_sop_text(self, skill_id: str) -> Optional[str]:
        # Exec skills usually don't have a pure SOP text body, they are code.
        # But if they define a __doc__ or 'prompt' meta, we could return it.
        # For now, default to None.
        return None
