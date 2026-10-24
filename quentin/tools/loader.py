from __future__ import annotations
import os
import yaml
import logging
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Optional
from quentin.tools.schemas import ToolSpec, ToolKind

logger = logging.getLogger(__name__)

class PluginLoader:
    """
    Tier 0 Plugin Loader (Marketplace Engine).
    Scans 'extensions/' for manifest.yaml and hot-loads tool logic.
    """
    def __init__(self, repo_root: str, tool_manager: Any):
        self.repo_root = Path(repo_root).resolve()
        self.extensions_dir = self.repo_root / "extensions"
        self.tool_manager = tool_manager

    def scan_and_load(self) -> List[str]:
        """
        Scans extensions directory and loads all valid plugins.
        Returns a list of loaded tool names.
        """
        loaded_tools = []
        if not self.extensions_dir.exists():
            return []

        for plugin_dir in self.extensions_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            
            manifest_path = plugin_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                tool_name = self._load_plugin(plugin_dir, manifest_path)
                if tool_name:
                    loaded_tools.append(tool_name)
            except Exception as e:
                logger.error(f"PluginLoader: Failed to load plugin from {plugin_dir}: {e}")

        return loaded_tools

    def _load_plugin(self, plugin_dir: Path, manifest_path: Path) -> Optional[str]:
        # 1. Parse Manifest
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        
        tool_name = manifest.get("name")
        logic_file = manifest.get("logic_file", "logic.py")
        description = manifest.get("description", "External plugin tool.")
        domain = manifest.get("domain", "extensions")

        if not tool_name:
            return None

        # 2. Load Logic
        logic_path = plugin_dir / logic_file
        if not logic_path.exists():
            logger.warning(f"Plugin {tool_name} missing logic file: {logic_file}")
            return None

        # Dynamic import
        spec_name = f"plugin_module_{tool_name.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(spec_name, str(logic_path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for a standard 'execute' function
            handler = getattr(module, "execute", None)
            if not handler:
                # Fallback to module-level call if handler not found
                handler = module

            # 3. Register in ToolManager
            tool_spec = ToolSpec(
                name=tool_name,
                description=description,
                domain=domain,
                kind=ToolKind.external,
                meta=manifest.get("meta", {})
            )
            
            self.tool_manager.register_tool(tool_spec, handler)
            logger.info(f"PluginLoader: Loaded {tool_name} from {plugin_dir}")
            return tool_name

        return None
