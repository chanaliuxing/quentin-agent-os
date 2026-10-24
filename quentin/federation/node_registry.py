from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List
import time

@dataclass
class FederationNode:
    node_id: str
    environment: str # "production", "staging", "dev"
    endpoint_url: str
    trust_level: str = "low" # "low", "medium", "high"
    capabilities: List[str] = field(default_factory=list)
    last_heartbeat: float = 0.0
    status: str = "active" # "active", "quarantined", "offline"

class NodeRegistry:
    """
    P7-A: Federation Node Registry
    Manages the lifecycle and discovery of federated nodes.
    """
    def __init__(self) -> None:
        self.nodes: Dict[str, FederationNode] = {}

    def register_node(self, node: FederationNode) -> None:
        self.nodes[node.node_id] = node
        node.last_heartbeat = time.time()

    def heartbeat(self, node_id: str) -> bool:
        if node_id in self.nodes:
            self.nodes[node_id].last_heartbeat = time.time()
            return True
        return False

    def get_node(self, node_id: str) -> Optional[FederationNode]:
        return self.nodes.get(node_id)

    def list_nodes(self, status_filter: Optional[str] = None) -> List[FederationNode]:
        if status_filter:
            return [n for n in self.nodes.values() if n.status == status_filter]
        return list(self.nodes.values())

    def quarantine_node(self, node_id: str) -> bool:
        if node_id in self.nodes:
            self.nodes[node_id].status = "quarantined"
            return True
        return False
