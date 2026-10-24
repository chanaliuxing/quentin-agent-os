from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from quentin.blueprint.tracker import BlueprintGapTracker, BlueprintScanReport
from quentin.runtime.task_queue import TaskQueue, TaskQueueItem
from quentin.observability.service import ObservabilityService
from quentin.runtime.task_sources_types import TaskSourceRunReport

try:
    from meta_agent.patchflow.queue import PatchQueue
except Exception:  # pragma: no cover
    PatchQueue = None  # type: ignore[assignment]

def enqueue_blueprint_gap_tasks(
    *,
    queue: TaskQueue,
    tracker: Optional[BlueprintGapTracker] = None,
    limit: int = 25,
    min_score: float = 1.0,
    domain: str = "core",
    environment: str = "sandbox",
    session_id: str = "brain",
) -> TaskSourceRunReport:
    tracker = tracker or BlueprintGapTracker()
    report: BlueprintScanReport = tracker.scan()

    existing = queue.load_all(limit=5000)
    already: set[str] = set()
    for it in existing:
        md = dict(it.metadata or {})
        if md.get("kind") == "blueprint_gap":
            cap = str(md.get("capability_id") or "")
            if cap:
                already.add(cap)

    enq = 0
    skipped = 0
    details: List[Dict[str, Any]] = []

    candidates: List[Any] = []
    for s in report.items:
        st = str(getattr(s, "status", "") or "").strip().lower()
        if st:
            if st != "done":
                candidates.append(s)
            continue
        if float(getattr(s, "score", 0.0)) < float(min_score):
            candidates.append(s)
    candidates.sort(
        key=lambda s: (
            float(getattr(s, "score", 0.0)),
            str(getattr(s.spec, "layer", "")),
            str(getattr(s.spec, "id", "")),
        )
    )

    for st in candidates[: max(0, int(limit or 0))]:
        cap_id = str(st.spec.id or "")
        if not cap_id:
            skipped += 1
            continue
        if cap_id in already:
            skipped += 1
            continue

        score = float(getattr(st, "score", 0.0))
        prio = int(round((1.0 - max(0.0, min(1.0, score))) * 10))

        item = TaskQueueItem.new(
            input_text=f"[maintenance] Blueprint gap: {cap_id} ({st.spec.name}).",
            domain=domain,
            environment=environment,
            session_id=session_id,
            priority=prio,
            metadata={
                "source": "task_source_blueprint",
                "kind": "blueprint_gap",
                "capability_id": cap_id,
                "blueprint_layer": str(st.spec.layer or ""),
                "blueprint_phase": str(st.spec.phase or ""),
                "score": score,
                "status": str(getattr(st, "status", "") or ""),
                "file_implemented": bool(getattr(st, "file_implemented", False)),
                "has_traces": bool(getattr(st, "has_traces", False)),
                "has_experiments": bool(getattr(st, "has_experiments", False)),
            },
        )
        queue.append(item)
        enq += 1
        details.append({"task_id": item.task_id, "capability_id": cap_id, "priority": prio, "score": score})

    from quentin.runtime.task_sources_types import TaskSourceRunReport
    return TaskSourceRunReport(enqueued=enq, skipped=skipped, details=details)


def enqueue_patchflow_backlog_tasks(
    *,
    queue: TaskQueue,
    limit: int = 25,
    domain: str = "core",
    environment: str = "sandbox",
    session_id: str = "brain",
) -> TaskSourceRunReport:
    if PatchQueue is None:
        return TaskSourceRunReport(enqueued=0, skipped=0, details=[])

    pq = PatchQueue()
    proposals = pq.load_all()

    existing = queue.load_all(limit=5000)
    already: set[str] = set()
    for it in existing:
        md = dict(it.metadata or {})
        if md.get("kind") == "patchflow_backlog":
            pid = str(md.get("patch_id") or "")
            if pid:
                already.add(pid)

    enq = 0
    skipped = 0
    details: List[Dict[str, Any]] = []

    backlog_statuses = {"needs_review", "blocked", "rejected", "rolled_back"}
    backlog = [p for p in proposals if str(getattr(p, "status", "") or "").strip() in backlog_statuses]
    backlog.sort(key=lambda p: (0 if str(p.status) == "needs_review" else 1, str(p.created_at or "")), reverse=False)

    for p in backlog[: max(0, int(limit or 0))]:
        pid = str(p.id or "")
        if not pid:
            skipped += 1
            continue
        if pid in already:
            skipped += 1
            continue
        st = str(p.status or "unknown")
        prio = 8 if st == "needs_review" else 5
        item = TaskQueueItem.new(
            input_text=f"[maintenance] PatchFlow backlog: {pid} status={st}.",
            domain=domain,
            environment=environment,
            session_id=session_id,
            priority=prio,
            metadata={
                "source": "task_source_patchflow",
                "kind": "patchflow_backlog",
                "patch_id": pid,
                "patch_status": st,
                "patch_source": str(getattr(p, "source", "") or ""),
                "intent": str(getattr(p, "intent", "") or "")[:500],
            },
        )
        queue.append(item)
        enq += 1
        details.append({"task_id": item.task_id, "patch_id": pid, "priority": prio, "status": st})

    from quentin.runtime.task_sources_types import TaskSourceRunReport
    return TaskSourceRunReport(enqueued=enq, skipped=skipped, details=details)


async def enqueue_anomaly_tasks(
    *,
    queue: TaskQueue,
    obs_service: Optional[ObservabilityService] = None,
    detector: Optional[Any] = None,
    limit: int = 10,
    domain: str = "core",
    environment: str = "sandbox",
    session_id: str = "brain",
) -> TaskSourceRunReport:
    try:
        from quentin.observability.anomaly_detector import AnomalyTaskGenerator
    except Exception:
        return TaskSourceRunReport(enqueued=0, skipped=0, details=[])

    obs_service = obs_service or ObservabilityService(repo_root=queue.repo_root)
    gen = detector or AnomalyTaskGenerator(obs_service, queue)

    generated_ids = await gen.check_and_generate()
    details = [{"task_id": tid, "source": "observability_anomaly"} for tid in generated_ids]
    return TaskSourceRunReport(enqueued=len(generated_ids), skipped=0, details=details)
