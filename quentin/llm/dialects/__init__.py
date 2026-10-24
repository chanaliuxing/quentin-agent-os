from __future__ import annotations

from quentin.llm.dialects.base import (
    PromptDialect,
    DialectRegistry,
    get_dialect_registry,
)
from quentin.llm.dialects.default_dialect import DefaultPromptDialect

def bootstrap_dialects(registry: DialectRegistry = None) -> DialectRegistry:
    if registry is None:
        registry = get_dialect_registry()
    
    registry.register(DefaultPromptDialect())
    return registry

__all__ = [
    "PromptDialect",
    "DialectRegistry",
    "get_dialect_registry",
    "bootstrap_dialects",
]
