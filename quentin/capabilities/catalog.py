from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

class CapabilityType(Enum):
    TOOL = "tool"
    SKILL = "skill"
    POLICY = "policy"
    ADAPTER = "adapter"

class LifecycleStatus(Enum):
    EXPERIMENTAL = "experimental"
    TRUSTED = "trusted"
    DEPRECATED = "deprecated"
    RETIRED = "retired"

@dataclass
class Capability:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: CapabilityType = CapabilityType.TOOL
    status: LifecycleStatus = LifecycleStatus.EXPERIMENTAL
    version: str = "v1.0.0"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

class CapabilityCatalog:
    """
    P4-D: Capability Catalog
    Tracks all system capabilities and their lifecycle status.
    """
    def __init__(self) -> None:
        self.capabilities: Dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self.capabilities[capability.id] = capability

    def get(self, capability_id: str) -> Optional[Capability]:
        return self.capabilities.get(capability_id)

    def list_all(self, type_filter: Optional[CapabilityType] = None) -> List[Capability]:
        if type_filter:
            return [c for c in self.capabilities.values() if c.type == type_filter]
        return list(self.capabilities.values())
