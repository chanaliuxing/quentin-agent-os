from __future__ import annotations
from typing import Dict, Any, List, Callable
from quentin.platform.sdk.base import BaseSDK, ExtensionManifest

class ToolSDK(BaseSDK):
    """
    P6-A: Tool SDK
    Standard interface for external tool providers.
    """
    def __init__(self, manifest: ExtensionManifest) -> None:
        super().__init__(manifest)
        self.tools: Dict[str, Callable] = {}

    def register_tool(self, name: str, handler: Callable, schema: Dict[str, Any]) -> None:
        self.tools[name] = {
            "handler": handler,
            "schema": schema
        }

    def get_capabilities(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "type": "tool", "schema": info["schema"]}
            for name, info in self.tools.items()
        ]
