from __future__ import annotations
from typing import Dict, List, Set

class KillSwitchMesh:
    """
    P10-C: Kill-Switch Mesh
    Hierarchical emergency shutdown mechanism.
    """
    def __init__(self) -> None:
        self.active_switches: Set[str] = set()

    def trigger(self, scope: str) -> None:
        """
        Scopes: "node:ID", "domain:D", "global"
        """
        self.active_switches.add(scope)

    def is_suppressed(self, node_id: str, domain: str) -> bool:
        if "global" in self.active_switches:
            return True
        if f"domain:{domain}" in self.active_switches:
            return True
        if f"node:{node_id}" in self.active_switches:
            return True
        return False

    def release(self, scope: str) -> None:
        if scope in self.active_switches:
            self.active_switches.remove(scope)
