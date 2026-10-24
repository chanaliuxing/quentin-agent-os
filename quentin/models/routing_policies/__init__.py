from __future__ import annotations

from typing import Any

from quentin.models.routing_policies.base import (
    RoutingPolicy,
    RoutingPolicyRegistry,
    get_routing_policy_registry,
)
from quentin.models.routing_policies.default_policy import DefaultRoutingPolicy
from quentin.models.routing_policies.multi_agent_policy import MultiAgentRoutingPolicy

def bootstrap_routing_policies(router: Any, registry: RoutingPolicyRegistry = None) -> RoutingPolicyRegistry:
    if registry is None:
        registry = get_routing_policy_registry()
    
    registry.register(DefaultRoutingPolicy(router=router))
    registry.register(MultiAgentRoutingPolicy(router=router))
    return registry

__all__ = [
    "RoutingPolicy",
    "RoutingPolicyRegistry",
    "get_routing_policy_registry",
    "bootstrap_routing_policies",
]
