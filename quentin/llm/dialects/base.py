from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

@runtime_checkable
class PromptDialect(Protocol):
    """
    Interface for pluggable prompt dialects (P3-C).
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def supports(self, provider: str, model_name: str) -> bool: ...

    def transform(
        self,
        provider: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Transform prompts based on model/provider quirks.
        """
        ...

class DialectRegistry:
    def __init__(self) -> None:
        self._dialects: Dict[str, PromptDialect] = {}

    def register(self, dialect: PromptDialect) -> None:
        self._dialects[dialect.id] = dialect
    
    def get(self, dialect_id: str) -> Optional[PromptDialect]:
        return self._dialects.get(str(dialect_id or "").strip())

    def list_dialects(self) -> List[PromptDialect]:
        return sorted(self._dialects.values(), key=lambda d: -d.priority)

    def apply(
        self,
        provider: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        md = metadata or {}
        for d in self.list_dialects():
            if d.supports(provider, model_name):
                return d.transform(provider, model_name, system_prompt, user_prompt, md)
        return system_prompt, user_prompt, md

    def apply_id(
        self,
        dialect_id: str,
        *,
        provider: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        md = metadata or {}
        d = self.get(dialect_id)
        if d is None:
            return self.apply(provider, model_name, system_prompt, user_prompt, md)
        if not d.supports(provider, model_name):
            return system_prompt, user_prompt, md
        return d.transform(provider, model_name, system_prompt, user_prompt, md)

# Global registry
_registry = DialectRegistry()

def get_dialect_registry() -> DialectRegistry:
    return _registry
