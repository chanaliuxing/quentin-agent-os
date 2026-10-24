from __future__ import annotations
from typing import List, Optional
from quentin.federation.node_registry import NodeRegistry, FederationNode

class FederationController:
    """
    P7-A: Federation Controller
    Orchestrates node discovery and task routing.
    """
    def __init__(self, registry: NodeRegistry) -> None:
        self.registry = registry

    def discover_capable_nodes(self, required_capability: str) -> List[FederationNode]:
        """
        Find active, trusted nodes with the required capability.
        """
        candidates = []
        for node in self.registry.list_nodes(status_filter="active"):
            if node.trust_level == "high" and required_capability in node.capabilities:
                candidates.append(node)
        return candidates

    def route_task(self, task_type: str) -> Optional[str]:
        """
        Simple routing: find first capable node.
        """
        nodes = self.discover_capable_nodes(task_type)
        if nodes:
            return nodes[0].node_id
        return None
