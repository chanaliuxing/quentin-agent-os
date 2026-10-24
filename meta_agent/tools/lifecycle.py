# meta_agent/tools/lifecycle.py
from __future__ import annotations
from typing import Optional, Dict, Any
import json

from meta_agent.tools.governance import CouncilBackedToolGate, ToolCouncilGate, guarded_update_lifecycle
from meta_agent.tools.registry import ToolLifecycle, ToolRegistry
from meta_agent.runtime.council_runtime import CouncilRuntime
from meta_agent.memory.types import MemoryRecord, MemoryTier
from meta_agent.memory.fabric import MemoryFabric
from meta_agent.tools.council_logger import log_council_votes


class ToolLifecycleManager:
    """
    Manages lifecycle transitions with optional AI Council gating.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        gate: Optional[ToolCouncilGate] = None,
        council: Optional[CouncilRuntime] = None,
        memory_fabric: Optional[MemoryFabric] = None,
    ) -> None:
        self.registry = registry
        self.memory_fabric = memory_fabric
        if gate:
            self.gate = gate
        elif council:
            self.gate = CouncilBackedToolGate(council=council)
            self.council = council
        else:
            self.gate = ToolCouncilGate()

    def upgrade_to_trusted(self, tool_id: str) -> bool:
        ok = guarded_update_lifecycle(self.registry, tool_id, ToolLifecycle.TRUSTED, self.gate)
        self._record_decision(tool_id, ok, target=ToolLifecycle.TRUSTED)
        return ok

    def deprecate(self, tool_id: str) -> bool:
        ok = guarded_update_lifecycle(self.registry, tool_id, ToolLifecycle.DEPRECATED, self.gate)
        self._record_decision(tool_id, ok, target=ToolLifecycle.DEPRECATED)
        return ok

    def set_state(self, tool_id: str, lifecycle: ToolLifecycle) -> bool:
        ok = guarded_update_lifecycle(self.registry, tool_id, lifecycle, self.gate)
        self._record_decision(tool_id, ok, target=lifecycle)
        return ok

    def _record_decision(self, tool_id: str, ok: bool, target: ToolLifecycle) -> None:
        reg = self.registry.get(tool_id)
        if not reg:
            return
        # Placeholder: persist decision into registry metadata for now.
        reg.governance.council_score = 1.0 if ok else 0.0
        if self.memory_fabric:
            council_raw: Dict[str, Any] = {}
            votes: list[dict[str, Any]] = []
            transcripts: Dict[str, str] = {}
            if hasattr(self, "gate") and hasattr(self.gate, "last_decision"):
                council_raw = self.gate.last_decision or {}
                votes = council_raw.get("votes", [])
                transcripts = council_raw.get("transcripts", {})
            decision = MemoryRecord.new(
                text=f"Lifecycle decision for {tool_id}: {target.value} ({'approved' if ok else 'rejected'})",
                tier=MemoryTier.MTS,
                kind="tool_lifecycle_decision",
                metadata={
                    "tool_id": tool_id,
                    "target_state": target.value,
                    "approved": ok,
                    "server": reg.server,
                    "risk_level": reg.governance.risk_level.value,
                    "council_score": reg.governance.council_score,
                    "council": council_raw,
                },
                importance=0.6,
            )
            self.memory_fabric.store.upsert(decision)
            log_council_votes(
                self.memory_fabric,
                proposal_id=f"tool:{tool_id}:{target.value}",
                tool_id=tool_id,
                target_state=target.value,
                votes=votes,
                approved=ok,
                transcripts=transcripts,
            )
