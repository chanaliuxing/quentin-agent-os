from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import os

from quentin.blueprint.tracker import BlueprintGapTracker, BlueprintItemStatus

logger = logging.getLogger(__name__)


try:
    from meta_agent.self_programming.engine_v2 import (
        SelfProgrammingConfig,
        SelfProgrammingEngineV2,
        GapLike,
    )
    from meta_agent.patches.store import PatchStore
except Exception:  # pragma: no cover
    SelfProgrammingEngineV2 = None  # type: ignore[assignment]
    SelfProgrammingConfig = None  # type: ignore[assignment]
    GapLike = None  # type: ignore[assignment]
    PatchStore = None  # type: ignore[assignment]


def _status_from_item(it: BlueprintItemStatus) -> str:
    s = str(getattr(it, "status", "") or "").strip().lower()
    if s in {"missing", "partial", "done", "unknown"}:
        return s
    if not it.file_implemented:
        return "missing"
    if it.has_traces and it.has_experiments:
        return "done"
    return "partial"


def _modules_from_item(it: BlueprintItemStatus) -> List[str]:
    hints = it.spec.hints or {}
    modules = hints.get("modules") or []
    out: List[str] = []
    for m in modules:
        if not m:
            continue
        out.append(str(m))
    return out


@dataclass(frozen=True)
class GapPatchResult:
    capability_id: str
    status_before: str
    patch_id: Optional[str]
    action: str
    reason: str
    targets: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GapAutoPatchReport:
    blueprint_path: str
    total_gaps: int
    attempted: int
    proposed: int
    skipped: int
    details: List[GapPatchResult]
    selfprog_ran: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_path": self.blueprint_path,
            "total_gaps": self.total_gaps,
            "attempted": self.attempted,
            "proposed": self.proposed,
            "skipped": self.skipped,
            "selfprog_ran": bool(self.selfprog_ran),
            "details": [d.to_dict() for d in self.details],
        }


class BlueprintGapAutoPatcher:
    """
    BlueprintGapAutoPatcher v2 (spec_v3.json):

    - Uses `quentin/blueprint/tracker.py:BlueprintGapTracker` to scan `blueprint/spec_v3.json`.
    - Derives "missing/partial/done" from (files, traces, experiments).
    - Optionally calls `meta_agent/self_programming/engine_v2.py:SelfProgrammingEngineV2` to propose patches.

    Safety:
    - Auto-apply is forcibly disabled in this entrypoint.
    - Running the self-programming engine is opt-in (`run_selfprog=True`).
    """

    def __init__(
        self,
        *,
        blueprint_path: str | Path = "blueprint/spec_v3.json",
    ) -> None:
        self.blueprint_path = str(blueprint_path)
        self.tracker = BlueprintGapTracker(spec_path=self.blueprint_path)

    def propose_patches_for_gaps(
        self,
        *,
        status_filter: List[str] = ("missing", "partial"),
        auto_eval: bool = False,
        run_selfprog: bool = False,
    ) -> GapAutoPatchReport:
        del auto_eval  # kept for CLI compatibility (SelfProgrammingEngineV2 does static evaluation internally)

        report = self.tracker.scan()
        target_statuses = {s.strip().lower() for s in list(status_filter or []) if str(s).strip()}
        if not target_statuses:
            target_statuses = {"missing", "partial"}

        candidates: List[BlueprintItemStatus] = []
        for it in report.items:
            status = _status_from_item(it)
            if status in target_statuses:
                candidates.append(it)

        details: List[GapPatchResult] = []
        gaps_for_engine: List[Any] = []

        for it in candidates:
            status = _status_from_item(it)
            modules = _modules_from_item(it)
            if not modules:
                details.append(
                    GapPatchResult(
                        capability_id=it.spec.id,
                        status_before=status,
                        patch_id=None,
                        action="skipped",
                        reason="Blueprint item has no hints.modules; cannot map to a target file.",
                        targets=[],
                    )
                )
                continue

            target_file = modules[0]
            reason_parts = []
            if not it.file_implemented:
                reason_parts.append("missing_files")
            if not it.has_traces:
                reason_parts.append("missing_traces")
            if not it.has_experiments:
                reason_parts.append("missing_experiments")
            reason = "gap:" + ",".join(reason_parts) if reason_parts else "gap"

            if run_selfprog and SelfProgrammingEngineV2 is not None and GapLike is not None:
                gaps_for_engine.append(
                    GapLike(
                        id=it.spec.id,
                        title=it.spec.name or it.spec.id,
                        description=it.spec.description or "",
                        category=it.spec.category or "blueprint_item",
                        priority=0 if status == "missing" else 1,
                        related_files=list(modules),
                        domain=None,
                        target_file=str(target_file),
                    )
                )

            details.append(
                GapPatchResult(
                    capability_id=it.spec.id,
                    status_before=status,
                    patch_id=None,
                    action="skipped",
                    reason="dry_run; use --run-selfprog to generate patch proposals",
                    targets=list(modules),
                )
            )

        selfprog_ran = False
        if run_selfprog and gaps_for_engine:
            if SelfProgrammingEngineV2 is None or SelfProgrammingConfig is None:
                logger.warning("BlueprintGapAutoPatcher: SelfProgrammingEngineV2 unavailable; skipping.")
            else:
                cfg = SelfProgrammingConfig(
                    allow_auto_apply=False,
                    max_gaps_per_cycle=int(os.getenv("QUENTIN_BLUEPRINT_AUTOPATCH_MAX_GAPS", "3") or "3"),
                )
                engine = SelfProgrammingEngineV2(config=cfg)
                backend = (os.getenv("CODER_BACKEND") or "").strip() or None
                engine.run_for_gaps(gaps_for_engine, backend=backend)
                selfprog_ran = True

                # Try to find patch_id by gap_id from PatchStore.
                try:
                    if PatchStore is not None:
                        store = PatchStore()
                        patches = store.list_patches(limit=200)
                        patch_by_gap: Dict[str, str] = {}
                        for p in sorted(patches, key=lambda x: getattr(x, "created_at", 0)):
                            gap_id = str((p.metadata or {}).get("gap_id") or "")
                            if gap_id:
                                patch_by_gap[gap_id] = p.id

                        new_details: List[GapPatchResult] = []
                        for d in details:
                            pid = patch_by_gap.get(d.capability_id)
                            if pid:
                                new_details.append(
                                    GapPatchResult(
                                        capability_id=d.capability_id,
                                        status_before=d.status_before,
                                        patch_id=pid,
                                        action="proposed",
                                        reason="patch_proposed_by_engine_v2",
                                        targets=list(d.targets),
                                    )
                                )
                            else:
                                new_details.append(d)
                        details = new_details
                except Exception:
                    logger.exception("BlueprintGapAutoPatcher: failed to map patch_id from PatchStore")

        total = len(candidates)
        proposed = sum(1 for d in details if d.action == "proposed")
        skipped = sum(1 for d in details if d.action == "skipped")

        return GapAutoPatchReport(
            blueprint_path=self.blueprint_path,
            total_gaps=total,
            attempted=total,
            proposed=proposed,
            skipped=skipped,
            details=details,
            selfprog_ran=selfprog_ran,
        )
