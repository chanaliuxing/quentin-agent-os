from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass
class StorageRecord:
    key: str
    value: Dict[str, Any]
    tags: List[str]
    importance: float = 0.5
    created_at: float = 0.0

@runtime_checkable
class KeyValueProvider(Protocol):
    """L0 Interface for simple key-value storage."""
    def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set(self, key: str, value: Dict[str, Any], tags: Optional[List[str]] = None) -> None: ...
    def list_keys(self, pattern: str = "*") -> List[str]: ...

@runtime_checkable
class VectorProvider(Protocol):
    """L0 Interface for vector search."""
    async def upsert(self, id: str, vector: List[float], metadata: Dict[str, Any]) -> None: ...
    async def search(self, vector: List[float], limit: int = 5) -> List[Dict[str, Any]]: ...

@runtime_checkable
class KnowledgeGraphProvider(Protocol):
    """L0 Interface for relational knowledge."""
    def add_relation(self, source: str, relation: str, target: str, props: Dict[str, Any]) -> None: ...
    def query(self, cypher: str) -> List[Any]: ...
