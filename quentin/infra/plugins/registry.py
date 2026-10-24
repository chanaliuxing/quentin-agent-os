from __future__ import annotations

import json
import logging
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PluginManifest:
    id: str
    version: str
    name: str
    permissions: List[str]
    entrypoint: str

class PluginRegistry:
    """
    Dynamic Plugin Management with Manifest Validation.
    Matches OpenClaw's plugin-sdk logic.
    """
    def __init__(self, plugin_dir: str = "mutable/plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: Dict[str, PluginManifest] = {}

    def discover_plugins(self):
        """Scans directories for manifest.json files."""
        for manifest_path in self.plugin_dir.glob("*/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text())
                manifest = PluginManifest(**data)
                self._plugins[manifest.id] = manifest
                logger.info(f"Plugin Registry: Loaded {manifest.name} v{manifest.version}")
            except Exception as e:
                logger.error(f"Failed to load plugin manifest at {manifest_path}: {e}")

    def get_plugin(self, plugin_id: str) -> Optional[PluginManifest]:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> List[PluginManifest]:
        return list(self._plugins.values())

# Global instance
plugin_registry = PluginRegistry()
