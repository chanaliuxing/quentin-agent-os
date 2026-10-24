from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class PluginInfo:
    id: str
    name: str
    version: str
    publisher: str
    download_url: str
    manifest_signature: str

class MarketIndex:
    """
    P6-B: Market Index
    Search and resolve plugin packages.
    """
    def __init__(self) -> None:
        self.plugins: Dict[str, PluginInfo] = {}

    def publish(self, info: PluginInfo) -> None:
        self.plugins[info.id] = info

    def search(self, query: str) -> List[PluginInfo]:
        return [p for p in self.plugins.values() if query.lower() in p.name.lower() or query.lower() in p.id.lower()]

    def resolve(self, plugin_id: str, version: Optional[str] = None) -> Optional[PluginInfo]:
        return self.plugins.get(plugin_id)
