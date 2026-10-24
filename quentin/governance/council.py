from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.governance.patch_council import PatchGovernanceCouncil, PatchDecision
from quentin.traces.core import TraceRecorder


@dataclass
class GovernanceDecision:
    decision_type: str
    decision: Dict[str, Any]


class GovernanceCouncil:
    """
    Governance council facade expected by the YAML blueprint.

    Today, the only concrete governance flow is patch governance. This wrapper provides
    a stable import path and a simple API that can be extended to broader governance
    decisions (experiments, deploys, tool policy updates) without breaking callers.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        council_callable: Any,
        trace_recorder: TraceRecorder,
    ) -> None:
        self._patch_council = PatchGovernanceCouncil(
            repo_root=repo_root,
            council_callable=council_callable,
            trace_recorder=trace_recorder,
        )

    def govern_patch(
        self,
        *,
        proposal_id: str,
        metrics: Dict[str, Any],
        immune_snapshot: Optional[Dict[str, Any]] = None,
        auto_apply: bool = False,
    ) -> PatchDecision:
        return self._patch_council.govern_patch(
            proposal_id=proposal_id,
            metrics=metrics,
            immune_snapshot=immune_snapshot,
            auto_apply=auto_apply,
        )

