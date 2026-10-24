from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from quentin.models.router import ModelInfo

@runtime_checkable
class RoutingPolicy(Protocol):
    """
    Interface for pluggable model routing policies (P3-C).
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def route(self, mode: str, task_type: str, metadata: Dict[str, Any]) -> Optional[ModelInfo]:
        """
        Choose a model based on mode and task.
        """
        ...

class RoutingPolicyRegistry:
    def __init__(self) -> None:
        self._policies: Dict[str, RoutingPolicy] = {}

    def register(self, policy: RoutingPolicy) -> None:
        self._policies[policy.id] = policy
    
    def get(self, policy_id: str) -> Optional[RoutingPolicy]:
        return self._policies.get(str(policy_id or "").strip())

    def list_policies(self) -> List[RoutingPolicy]:
        return sorted(self._policies.values(), key=lambda p: -p.priority)

    def route(self, mode: str, task_type: str, metadata: Dict[str, Any]) -> Optional[ModelInfo]:
        for p in self.list_policies():
            res = p.route(mode, task_type, metadata)
            if res:
                return res
        return None

    def route_id(self, policy_id: str, *, mode: str, task_type: str, metadata: Dict[str, Any]) -> Optional[ModelInfo]:
        p = self.get(policy_id)
        if p is None:
            return None
        return p.route(mode, task_type, metadata)

# Global registry
_registry = RoutingPolicyRegistry()

def get_routing_policy_registry() -> RoutingPolicyRegistry:
    return _registry
