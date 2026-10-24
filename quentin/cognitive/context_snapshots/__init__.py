from __future__ import annotations

from quentin.cognitive.context_snapshots.base import (
    ContextSnapshotProvider,
    ContextSnapshotRegistry,
    SnapshotBlock,
    get_context_snapshot_registry,
    is_context_snapshots_enabled,
)
from quentin.cognitive.context_snapshots.file_tree import FileTreeSnapshotProvider
from quentin.cognitive.context_snapshots.git_status import GitStatusSnapshotProvider
from quentin.cognitive.context_snapshots.tool_plugins import ToolPluginsSnapshotProvider
from quentin.cognitive.context_snapshots.tool_inventory import ToolInventorySnapshotProvider
from quentin.cognitive.context_snapshots.bootstrap_files import BootstrapFilesProvider

def bootstrap_snapshots(registry: ContextSnapshotRegistry = None) -> ContextSnapshotRegistry:
    if registry is None:
        registry = get_context_snapshot_registry()
        
    registry.register(BootstrapFilesProvider())
    registry.register(FileTreeSnapshotProvider())
    registry.register(GitStatusSnapshotProvider())
    registry.register(ToolPluginsSnapshotProvider())
    registry.register(ToolInventorySnapshotProvider())
    
    return registry

__all__ = [
    "ContextSnapshotProvider",
    "ContextSnapshotRegistry",
    "SnapshotBlock",
    "get_context_snapshot_registry",
    "is_context_snapshots_enabled",
    "bootstrap_snapshots",
]
