from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class ExtensionManifest:
    name: str
    version: str
    author: str
    description: str
    permissions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class BaseSDK(ABC):
    """
    P6-A: Base Platform SDK
    Common interface for all Quentin extensions.
    """
    def __init__(self, manifest: ExtensionManifest) -> None:
        self.manifest = manifest

    @abstractmethod
    def get_capabilities(self) -> List[Dict[str, Any]]:
        pass
