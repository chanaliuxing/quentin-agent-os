from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable
from quentin.skills.schema import SkillSpec

@runtime_checkable
class SkillBackend(Protocol):
    """
    Interface for pluggable skill storage/discovery backends (P2-A).
    """

    @property
    def id(self) -> str:
        """Unique identifier for this backend instance."""
        ...

    @property
    def priority(self) -> int:
        """Higher priority backends are checked first for skill loading."""
        ...

    def list_skills(self, domain: str | None = None) -> List[SkillSpec]:
        """
        List all available skills from this backend, optionally filtered by domain.
        Returns standardized SkillSpec objects (metadata only).
        """
        ...

    def load_exec_callable(self, skill_id: str) -> Tuple[Optional[Callable[..., Any]], Optional[Any]]:
        """
        Load an executable python callable for the given skill ID.
        Returns (callable, plugin_metadata) or (None, None).
        """
        ...

    def load_sop_text(self, skill_id: str) -> Optional[str]:
        """
        Load the markdown SOP text (system prompt body) for the given skill ID.
        Returns text content or None.
        """
        ...


class SkillBackendRegistry:
    """
    Registry for managing multiple skill backends.
    """

    def __init__(self) -> None:
        self._backends: Dict[str, SkillBackend] = {}

    def register(self, backend: SkillBackend) -> None:
        self._backends[backend.id] = backend

    def list_backends(self) -> List[SkillBackend]:
        def _prio(b: SkillBackend) -> int:
            try:
                return int(getattr(b, "priority", 0) or 0)
            except Exception:
                return 0

        return sorted(self._backends.values(), key=lambda b: (-_prio(b), str(getattr(b, "id", ""))))

    def get_backend(self, backend_id: str) -> Optional[SkillBackend]:
        return self._backends.get(backend_id)


# Global registry instance
_registry = SkillBackendRegistry()


def get_skill_backend_registry() -> SkillBackendRegistry:
    return _registry
