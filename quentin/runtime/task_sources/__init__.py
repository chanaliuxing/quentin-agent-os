from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from quentin.runtime.task_queue import TaskQueue
from quentin.runtime.task_source_registry import (
    CombinedTaskSourcesReport,
    TaskSourceContext,
    TaskSourceRegistry,
)
from quentin.runtime.task_sources_types import TaskSourceRunReport
from quentin.runtime.task_enqueue_utils import (
    enqueue_blueprint_gap_tasks,
    enqueue_anomaly_tasks,
)
from quentin.runtime.task_sources.blueprint import BlueprintTaskSource
from quentin.runtime.task_sources.patchflow import PatchflowTaskSource
from quentin.runtime.task_sources.anomaly import ObservabilityAnomalyTaskSource
from quentin.runtime.task_sources.skill_mining import SkillMiningTaskSource

try:
    from meta_agent.patchflow.queue import PatchQueue
except Exception:  # pragma: no cover
    PatchQueue = None  # type: ignore[assignment]


def enqueue_patchflow_backlog_tasks(
    *,
    queue: TaskQueue,
    limit: int = 25,
    domain: str = "core",
    environment: str = "sandbox",
    session_id: str = "brain",
) -> TaskSourceRunReport:
    """
    Task source wrapper for PatchFlow backlog.

    Note: This implementation intentionally uses the `PatchQueue` symbol from this
    module so unit tests can monkeypatch `quentin.runtime.task_sources.PatchQueue`.
    """
    from quentin.runtime.task_queue import TaskQueueItem

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
        pid = str(getattr(p, "id", "") or "")
        if not pid:
            skipped += 1
            continue
        if pid in already:
            skipped += 1
            continue
        st = str(getattr(p, "status", "unknown") or "unknown")
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

    return TaskSourceRunReport(enqueued=enq, skipped=skipped, details=details)


def _bool_env(name: str, default: str = "1") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


from dataclasses import dataclass

@dataclass(frozen=True)
class TaskSourcesCombinedReport:
    """
    Combined report for registry mode.
    """
    enqueued: int
    skipped: int
    details: List[Dict[str, Any]]
    sources: List[Any] # List[RegistryTaskSourceRunReport]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enqueued": int(self.enqueued),
            "skipped": int(self.skipped),
            "details": list(self.details),
            "sources": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.sources],
        }


def build_default_task_source_registry() -> TaskSourceRegistry:
    reg = TaskSourceRegistry()
    reg.register(BlueprintTaskSource())
    reg.register(PatchflowTaskSource())
    reg.register(ObservabilityAnomalyTaskSource())
    reg.register(SkillMiningTaskSource())
    try:
        reg.load_bootstrap_hooks_from_env()
    except Exception:
        pass
    return reg


def _summarize_sources(reports: List[Any]) -> str:
    bits: List[str] = []
    for r in reports:
        sid = getattr(r, "source_id", "unknown")
        status = getattr(r, "status", "unknown")
        reason = getattr(r, "reason", "unknown")
        enq = int(getattr(r, "enqueued", 0))
        err = int(getattr(r, "errors", 0))
        bits.append(f"{sid}:{status}:{reason}:enq={enq}:err={err}")
    return "; ".join(bits)[:2000]


async def run_task_sources_once(
    *,
    repo_root: str = ".",
    max_blueprint_tasks: int = 25,
) -> TaskSourcesCombinedReport:
    """
    Run enabled task sources once and enqueue tasks.
    """
    root = Path(repo_root).resolve()
    q = TaskQueue(repo_root=str(root))

    domain = str(os.getenv("QUENTIN_TASK_DOMAIN", "core") or "core")
    environment = str(os.getenv("QUENTIN_TASK_ENVIRONMENT", "sandbox") or "sandbox")
    session_id = str(os.getenv("QUENTIN_TASK_SESSION_ID", "brain") or "brain")

    use_registry = _bool_env("QUENTIN_TASK_SOURCES_REGISTRY", "0")
    if use_registry:
        reg = build_default_task_source_registry()
        ctx = TaskSourceContext(repo_root=root, queue=q, domain=domain, environment=environment, session_id=session_id)
        ctx.env["QUENTIN_TASK_SOURCE_BLUEPRINT_MAX"] = str(int(max_blueprint_tasks))
        combined: CombinedTaskSourcesReport = await reg.run_enabled(ctx)
        return TaskSourcesCombinedReport(
            enqueued=int(combined.enqueued),
            skipped=int(combined.skipped),
            details=list(combined.details),
            sources=list(combined.sources),
        )

    # Legacy behavior (no registry)
    total_enq = 0
    total_skip = 0
    details: List[Dict[str, Any]] = []
    sources: List[Any] = []

    if _bool_env("QUENTIN_TASK_SOURCE_BLUEPRINT", "1"):
        r = enqueue_blueprint_gap_tasks(queue=q, limit=int(max_blueprint_tasks), domain=domain, environment=environment, session_id=session_id)
        total_enq += int(r.enqueued)
        total_skip += int(r.skipped)
        details.extend(r.details)
        from quentin.runtime.task_source_registry import TaskSourceRunReport as RegistryTaskSourceRunReport
        sources.append(
            RegistryTaskSourceRunReport(
                source_id="blueprint",
                status="ok",
                reason="ok" if int(r.enqueued) > 0 else "no_candidates",
                enqueued=int(r.enqueued),
                skipped=int(r.skipped),
                details=list(r.details),
            )
        )

    if _bool_env("QUENTIN_TASK_SOURCE_PATCHFLOW", "1") and PatchQueue is not None:
        r = enqueue_patchflow_backlog_tasks(
            queue=q,
            limit=int(os.getenv("QUENTIN_TASK_SOURCE_PATCHFLOW_MAX", "25") or "25"),
            domain=domain,
            environment=environment,
            session_id=session_id,
        )
        total_enq += int(r.enqueued)
        total_skip += int(r.skipped)
        details.extend(r.details)
        from quentin.runtime.task_source_registry import TaskSourceRunReport as RegistryTaskSourceRunReport
        sources.append(
            RegistryTaskSourceRunReport(
                source_id="patchflow",
                status="ok",
                reason="ok" if int(r.enqueued) > 0 else "no_candidates",
                enqueued=int(r.enqueued),
                skipped=int(r.skipped),
                details=list(r.details),
            )
        )

    if _bool_env("QUENTIN_TASK_SOURCE_OBS", "1"):
        r = await enqueue_anomaly_tasks(
            queue=q,
            limit=int(os.getenv("QUENTIN_TASK_SOURCE_OBS_MAX", "10") or "10"),
            domain=domain,
            environment=environment,
            session_id=session_id,
        )
        total_enq += int(r.enqueued)
        total_skip += int(r.skipped)
        details.extend(r.details)
        from quentin.runtime.task_source_registry import TaskSourceRunReport as RegistryTaskSourceRunReport
        sources.append(
            RegistryTaskSourceRunReport(
                source_id="obs",
                status="ok",
                reason="ok" if int(r.enqueued) > 0 else "no_candidates",
                enqueued=int(r.enqueued),
                skipped=int(r.skipped),
                details=list(r.details),
            )
        )

    details.append({"kind": "task_sources_summary", "summary": _summarize_sources(sources)})
    return TaskSourcesCombinedReport(enqueued=total_enq, skipped=total_skip, details=details, sources=sources)
