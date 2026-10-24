# meta_agent/tools/governance.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from meta_agent.tools.registry import RiskLevel, ToolLifecycle, ToolRegistration, ToolRegistry
from meta_agent.runtime.council_runtime import CouncilRuntime, CouncilResult, CouncilTask
import asyncio


class ToolCouncilGate:
    """
    Placeholder governance guard for lifecycle upgrades.

    Real implementations can plug in AI Council deliberation; default guard
    simply allows low/medium risk upgrades and forces callers to explicitly
    approve high-risk transitions.
    """

    def __init__(self, approval_fn: Optional[Callable[[ToolRegistration, ToolLifecycle], bool]] = None) -> None:
        self.approval_fn = approval_fn

    def approve(self, registration: ToolRegistration, target: ToolLifecycle) -> bool:
        if self.approval_fn:
            return bool(self.approval_fn(registration, target))
        if registration.governance.risk_level == RiskLevel.HIGH:
            # Defer HIGH risk upgrades to explicit approval.
            return target != ToolLifecycle.TRUSTED
        return True


def guarded_update_lifecycle(
    registry: ToolRegistry,
    tool_id: str,
    target: ToolLifecycle,
    gate: Optional[ToolCouncilGate] = None,
) -> bool:
    registration = registry.get(tool_id)
    if not registration:
        raise KeyError(f"tool not found: {tool_id}")
    if gate and not gate.approve(registration, target):
        return False
    registry.update_lifecycle(tool_id, target)
    return True


class CouncilBackedToolGate(ToolCouncilGate):
    """
    Uses CouncilRuntime to deliberate lifecycle upgrades. Supports multiple roles (votes).
    """

    def __init__(self, council: CouncilRuntime, roles: Optional[list[str]] = None) -> None:
        super().__init__()
        self.council = council
        self.roles = roles or ["RiskAgent", "CapabilityAgent", "CostAgent"]
        self.last_decision: Dict[str, Any] = {}

    def approve(self, registration: ToolRegistration, target: ToolLifecycle) -> bool:
        if target != ToolLifecycle.TRUSTED:
            return super().approve(registration, target)

        schema_hint = """{
          "decision": "approve | reject | revise",
          "rationale": "short reason",
          "constraints": "optional additional constraints"
        }"""
        context = {
            "tool_id": registration.tool_id,
            "server": registration.server,
            "transport": registration.transport,
            "uri": registration.uri,
            "risk_level": registration.governance.risk_level.value,
            "current_state": registration.governance.lifecycle.value,
            "target_state": target.value,
        }

        votes: list[dict[str, Any]] = []
        transcripts: Dict[str, str] = {}
        for role in self.roles:
            async def _ask():
                task = CouncilTask(role=role, question="Should this tool be upgraded to trusted?", context=context, json_schema_hint=schema_hint)
                return await self.council.deliberate(task)

            try:
                result: CouncilResult = asyncio.run(_ask())
            except RuntimeError:
                continue
            if result:
                vote_json = result.final_json or {}
                vote_json["role"] = role
                votes.append(vote_json)
                transcripts[role] = "\n".join(
                    [
                        f"[planner]\n{result.raw_planner}",
                        f"[critic]\n{result.raw_critic}",
                        f"[judge]\n{result.raw_judge}",
                    ]
                )

        self.last_decision = {"votes": votes, "transcripts": transcripts}
        # Aggregation: approve if majority approve, otherwise reject.
        # This allows a majority to override individual rejects.
        num_approvals = len([v for v in votes if v.get("decision", "").lower() == "approve"])
        num_rejects = len([v for v in votes if v.get("decision", "").lower() == "reject"])
        num_total_votes = len(votes)

        if num_total_votes == 0:
            return False # No votes, no approval

        if num_approvals > num_rejects and num_approvals > 0:
            return True
        
        return False # Default to reject if no clear majority approve
