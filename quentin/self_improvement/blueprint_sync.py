from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from quentin.blueprint.capability_scanner import CapabilityScanner
from quentin.blueprint.gap_tracker import BlueprintGapTracker, CapabilitiesRegistry
from quentin.blueprint.spec import BlueprintSpec, load_default_spec_v3
from quentin.self_improvement.manager import SelfImprovementManager
from quentin.self_improvement.schemas import (
    ImprovementTask,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    TASK_STATUS_PENDING,
)

logger = logging.getLogger(__name__)


@dataclass
class BlueprintSyncReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BlueprintImprovementSync:
    """
    Blueprint-driven improvement task sync (v3 canonical).

    Source of truth:
    - `quentin/blueprint/spec.py:load_default_spec_v3()` for machine-readable capabilities
    - `CapabilityScanner` for evidence updates into `CapabilitiesRegistry`
    - `BlueprintGapTracker` for gap report (missing/partial/ok/unknown)
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        spec: Optional[BlueprintSpec] = None,
        registry: Optional[CapabilitiesRegistry] = None,
        si_manager: Optional[SelfImprovementManager] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.spec = spec or load_default_spec_v3()
        self.registry = registry or CapabilitiesRegistry(repo_root=self.repo_root)
        self.scanner = CapabilityScanner(repo_root=self.repo_root, spec=self.spec, registry=self.registry)
        self.gap_tracker = BlueprintGapTracker(spec=self.spec, registry=self.registry, repo_root=self.repo_root)
        self.si_manager = si_manager or SelfImprovementManager(path=str(self.repo_root / "data" / "improvement_tasks.json"))

    def sync(self, *, include_statuses: Optional[List[str]] = None) -> BlueprintSyncReport:
        """
        1) Scan capabilities and update registry (static evidence).
        2) Create/refresh ImprovementTask entries for missing/partial capabilities.
        """
        include = {s.lower() for s in include_statuses} if include_statuses else None

        self.scanner.scan_and_update_registry()
        report = self.gap_tracker.scan()

        existing = {t.task_id: t for t in self.si_manager.list_tasks()}
        out = BlueprintSyncReport()

        def upsert_for(cap_id: str, overall_status: str) -> None:
            cap = self.spec.get_capability(cap_id)
            if not cap:
                return
            if include and overall_status.lower() not in include:
                out.skipped += 1
                return

            task_id = f"bp::{cap.id}"
            priority = PRIORITY_HIGH if overall_status == "missing" else PRIORITY_MEDIUM

            current_status = self.registry.get(cap.id)
            evidence = current_status.evidence if current_status else None

            task = existing.get(task_id)
            if task is None:
                task = ImprovementTask(
                    task_id=task_id,
                    capability=cap.id,
                    requirement_id=None,
                    overall_status=overall_status,
                    status=TASK_STATUS_PENDING,
                    priority=priority,
                    title=cap.name,
                    description=cap.description,
                    meta={
                        "section": cap.section,
                        "maturity_target": cap.maturity_target,
                        "evidence": evidence,
                    },
                )
                self.si_manager.upsert_task(task)
                out.created += 1
                return

            changed = False
            if task.overall_status != overall_status:
                task.overall_status = overall_status
                changed = True
            if task.priority != priority:
                task.priority = priority
                changed = True
            if task.title != cap.name:
                task.title = cap.name
                changed = True
            if task.description != cap.description:
                task.description = cap.description
                changed = True
            task.meta.setdefault("section", cap.section)
            task.meta.setdefault("maturity_target", cap.maturity_target)
            if evidence and task.meta.get("evidence") != evidence:
                task.meta["evidence"] = evidence
                changed = True

            if changed:
                self.si_manager.upsert_task(task)
                out.updated += 1
            else:
                out.skipped += 1

        for g in report.missing:
            upsert_for(g.capability.id, "missing")
        for g in report.partial:
            upsert_for(g.capability.id, "partial")

        logger.info("BlueprintImprovementSync: %s", out.to_dict())
        return out

