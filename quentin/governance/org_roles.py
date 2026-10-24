from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set, Dict

@dataclass
class OrgRole:
    name: str
    permissions: Set[str] = field(default_factory=set)

class RoleManager:
    """
    P7-C: Organization Role Manager (RBAC)
    """
    def __init__(self) -> None:
        self.roles: Dict[str, OrgRole] = {}
        self._bootstrap_roles()

    def _bootstrap_roles(self) -> None:
        self.roles["operator"] = OrgRole("operator", {"run_task", "view_metrics"})
        self.roles["admin"] = OrgRole("admin", {"run_task", "view_metrics", "manage_nodes", "approve_policy"})
        self.roles["auditor"] = OrgRole("auditor", {"view_audit_logs"})

    def has_permission(self, role_name: str, permission: str) -> bool:
        role = self.roles.get(role_name)
        if not role:
            return False
        return permission in role.permissions
