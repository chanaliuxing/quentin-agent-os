from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import logging
import os
import time

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SnapshotBlock:
    """
    A single bounded block of context information.
    """
    id: str
    title: str
    content: str
    ttl_sec: int = 60
    size_bytes: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class ContextSnapshotProvider(Protocol):
    """
    Interface for context snapshot providers (P1-E).
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]: ...


class ContextSnapshotRegistry:
    """
    Registry for pluggable context snapshot providers.
    """
    def __init__(self) -> None:
        self._providers: Dict[str, ContextSnapshotProvider] = {}

    def register(self, provider: ContextSnapshotProvider) -> None:
        self._providers[provider.id] = provider

    def list_providers(self) -> List[ContextSnapshotProvider]:
        return sorted(self._providers.values(), key=lambda p: -p.priority)

    def collect_all(self, repo_root: Path, context: Dict[str, Any], max_total_bytes: int = 32768) -> List[SnapshotBlock]:
        blocks: List[SnapshotBlock] = []
        total_bytes = 0
        
        for p in self.list_providers():
            try:
                block = p.collect(repo_root, context)
                if not block:
                    continue
                
                block_size = len(block.content.encode("utf-8"))
                if total_bytes + block_size > max_total_bytes:
                    logger.warning(f"Snapshot block {p.id} exceeds total budget, skipping.")
                    continue
                
                blocks.append(block)
                total_bytes += block_size
            except Exception as e:
                logger.error(f"Provider {p.id} failed to collect snapshot: {e}")
                
        return blocks

# Global registry instance
_registry = ContextSnapshotRegistry()

def get_context_snapshot_registry() -> ContextSnapshotRegistry:
    return _registry

def _bool_env(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

def is_context_snapshots_enabled() -> bool:
    return _bool_env("QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS", "0")
