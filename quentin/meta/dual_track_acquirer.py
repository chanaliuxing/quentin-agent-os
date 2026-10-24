from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from quentin.config.dual_track import DualTrackConfig
from quentin.config.mcp_security import MCPSecurityConfig
from quentin.governance.tool_council import ToolCandidate, ToolGovernanceGate
from quentin.memory.kinds import KIND_CAPABILITY_ACQUISITION_REQUEST
from quentin.memory.models import MemoryTier
from quentin.meta.capability_gap import CapabilityGap
from quentin.meta.dual_track_router import DualTrackDecision
from quentin.utils.time import now_utc_iso


@dataclass(frozen=True)
class AcquisitionRequest:
    request_id: str
    track: str  # "mcp" | "self_programming"
    domain: str
    environment: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "track": self.track,
            "domain": self.domain,
            "environment": self.environment,
            "payload": dict(self.payload or {}),
        }


class DualTrackAcquirer:
    """
    v0 acquirer: enqueue governed acquisition requests into memory (no auto-install/auto-patch).

    This keeps the system modular:
    - routing is separate (DualTrackRouter)
    - governance is separate (ToolGovernanceGate / PatchCouncil)
    - execution of acquisition is handled by later loops / operators
    """

    def __init__(
        self,
        *,
        repo_root: str,
        memory_fabric: Any,
        dual_track_config: DualTrackConfig,
        mcp_security: MCPSecurityConfig,
        council_manager: Any,
        tool_governance_gate: Optional[ToolGovernanceGate] = None,
    ) -> None:
        self.repo_root = repo_root
        self.memory_fabric = memory_fabric
        self.cfg = dual_track_config
        self.mcp_security = mcp_security
        self.council_manager = council_manager
        self.tool_gate = tool_governance_gate

    def _env_allowed(self, env: str) -> bool:
        e = str(env or "sandbox").strip().lower()
        if e == "sandbox":
            return True
        if e == "staging":
            return bool(self.cfg.allow_in_staging)
        if e == "prod":
            return bool(self.cfg.allow_in_prod)
        return False

    def maybe_enqueue(
        self,
        *,
        gap: CapabilityGap,
        decision: DualTrackDecision,
        ctx: Dict[str, Any],
    ) -> Optional[AcquisitionRequest]:
        if not bool(self.cfg.enabled):
            return None

        domain = str(gap.domain or "core").strip().lower()
        env = str(gap.environment or "sandbox").strip().lower()
        if domain in {str(x).strip().lower() for x in (self.cfg.blocked_domains or [])}:
            return None
        if not self._env_allowed(env):
            return None

        track = str(decision.track or "").strip().lower()
        if track == "mcp":
            # Optional tool governance: if enabled, require an explicit non-reject vote before enqueuing.
            if bool(self.cfg.require_tool_governance) and bool(self.mcp_security.enable_tool_governance):
                gate = self.tool_gate or ToolGovernanceGate(council_manager=self.council_manager)
                cand = ToolCandidate(
                    tool_id=str(gap.tool_name or ""),
                    signature=str((gap.meta or {}).get("signature") or ""),
                    description=str(gap.gap_text or ""),
                    categories=[],
                    source="capability_gap",
                    meta={"gap_id": gap.gap_id},
                )
                gov = gate.decide(candidate=cand, context={"env": env, "domain": domain, **(ctx or {})})
                if str(gov.verdict or "") == "reject":
                    return None
                gov_dict = gov.to_dict()
            else:
                gov_dict = {"verdict": "sandbox_only", "rationale": "tool_governance_disabled_or_not_required"}

            payload = {
                "gap": gap.to_dict(),
                "decision": decision.to_dict(),
                "tool_governance": gov_dict,
                "requested_at": now_utc_iso(),
            }
            return AcquisitionRequest(
                request_id=f"acq_{gap.gap_id}",
                track="mcp",
                domain=domain,
                environment=env,
                payload=payload,
            )

        if track == "self_programming":
            payload = {
                "gap": gap.to_dict(),
                "decision": decision.to_dict(),
                "requires_patch_governance": bool(self.cfg.require_patch_governance),
                "requested_at": now_utc_iso(),
            }
            return AcquisitionRequest(
                request_id=f"acq_{gap.gap_id}",
                track="self_programming",
                domain=domain,
                environment=env,
                payload=payload,
            )
        return None

    def write_request(self, req: AcquisitionRequest, *, tier: MemoryTier = MemoryTier.STS) -> None:
        self.memory_fabric.remember_atomic(
            content=f"CAPABILITY_ACQUISITION_REQUEST: track={req.track} gap={req.payload.get('gap', {}).get('gap_text', '')}",
            source="dual_track_acquirer",
            tier=tier,
            domain=req.domain,
            importance=0.6,
            tags=["capability_acquisition", f"track:{req.track}", req.domain, req.environment],
            metadata=req.to_dict(),
            kind=KIND_CAPABILITY_ACQUISITION_REQUEST,
        )

