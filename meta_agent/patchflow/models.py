# meta_agent/patchflow/models.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import uuid
import datetime as dt


@dataclass
class PatchProposal:
    id: str
    source: str
    kind: str
    patch_format: str
    targets: List[str]
    body: Dict[str, Any]
    intent: str
    reason: str
    blueprint_context: str
    created_by: str
    created_at: str
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(
        source: str,
        kind: str,
        patch_format: str,
        targets: List[str],
        body: Dict[str, Any],
        intent: str,
        reason: str,
        blueprint_context: str,
        created_by: str = "meta-agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PatchProposal":
        return PatchProposal(
            id=f"patch-{uuid.uuid4().hex[:8]}",
            source=source,
            kind=kind,
            patch_format=patch_format,
            targets=targets,
            body=body,
            intent=intent,
            reason=reason,
            blueprint_context=blueprint_context,
            created_by=created_by,
            created_at=now_iso(),
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PatchProposal":
        return PatchProposal(**d)
