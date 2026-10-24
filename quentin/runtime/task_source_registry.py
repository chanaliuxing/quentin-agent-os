from __future__ import annotations

from dataclasses import dataclass, asdict, field
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence
import inspect
import os
import time


@dataclass(frozen=True)
class TaskSourceSpec:
    id: str
    name: str
    kind: str
    priority: int = 0
    default_enabled: bool = True
    max_per_run: int = 25
    cooldown_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskSourceContext:
    repo_root: Path
    queue: Any
    domain: str
    environment: str
    session_id: str
    now_ts: float = field(default_factory=lambda: time.time())
    env: Dict[str, str] = field(default_factory=lambda: dict(os.environ))


@dataclass(frozen=True)
class TaskSourceRunReport:
    source_id: str
    status: str
    reason: str
    enqueued: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "reason": self.reason,
            "enqueued": int(self.enqueued),
            "skipped": int(self.skipped),
            "errors": int(self.errors),
            "duration_ms": float(self.duration_ms),
            "details": list(self.details),
        }


@dataclass(frozen=True)
class CombinedTaskSourcesReport:
    enqueued: int
    skipped: int
    details: List[Dict[str, Any]]
    sources: List[TaskSourceRunReport] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enqueued": int(self.enqueued),
            "skipped": int(self.skipped),
            "details": list(self.details),
            "sources": [s.to_dict() for s in self.sources],
        }


class TaskSource(Protocol):
    @property
    def spec(self) -> TaskSourceSpec: ...

    def enabled(self, ctx: TaskSourceContext) -> bool: ...

    def max_per_run(self, ctx: TaskSourceContext) -> int: ...

    async def run(self, ctx: TaskSourceContext) -> TaskSourceRunReport: ...


def _parse_bool_env(v: str, *, default: bool) -> bool:
    s = str(v or "").strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "on")


def _import_object(path: str) -> Any:
    mod_path, _, attr = path.rpartition(".")
    if not mod_path:
        raise ValueError(f"Invalid import path: {path}")
    mod = import_module(mod_path)
    return getattr(mod, attr)


class TaskSourceRegistry:
    """
    Registry for pluggable task sources (P1-A).

    - Keeps core runtime stable while allowing new sources to be added by registration.
    - Provides structured run reports so the brain can sense why work was not enqueued.
    """

    def __init__(self) -> None:
        self._sources: Dict[str, TaskSource] = {}
        self._last_run_at: Dict[str, float] = {}

    def register(self, source: TaskSource) -> None:
        sid = str(source.spec.id or "").strip()
        if not sid:
            raise ValueError("TaskSource.spec.id must be non-empty")
        self._sources[sid] = source

    def list_specs(self) -> List[TaskSourceSpec]:
        return [s.spec for s in self._ordered_sources()]

    def load_bootstrap_hooks_from_env(self, *, env_var: str = "QUENTIN_TASK_SOURCES_BOOTSTRAP") -> List[str]:
        """
        Optional pluggability: call bootstrap hooks referenced by env var.
        Value: comma-separated dotted callables, each called with `(registry)`.
        """
        raw = str(os.getenv(env_var, "") or "").strip()
        if not raw:
            return []
        loaded: List[str] = []
        for part in raw.split(","):
            p = part.strip()
            if not p:
                continue
            fn = _import_object(p)
            if not callable(fn):
                raise TypeError(f"Bootstrap hook not callable: {p}")
            fn(self)
            loaded.append(p)
        return loaded

    async def run_enabled(self, ctx: TaskSourceContext) -> CombinedTaskSourcesReport:
        total_enq = 0
        total_skip = 0
        task_details: List[Dict[str, Any]] = []
        source_reports: List[TaskSourceRunReport] = []

        for source in self._ordered_sources():
            spec = source.spec
            sid = str(spec.id)

            if not source.enabled(ctx):
                source_reports.append(
                    TaskSourceRunReport(
                        source_id=sid,
                        status="skipped",
                        reason="disabled",
                        enqueued=0,
                        skipped=0,
                        errors=0,
                        duration_ms=0.0,
                        details=[],
                    )
                )
                continue

            cooldown = float(spec.cooldown_sec or 0.0)
            last = float(self._last_run_at.get(sid, 0.0) or 0.0)
            if cooldown > 0.0 and (ctx.now_ts - last) < cooldown:
                source_reports.append(
                    TaskSourceRunReport(
                        source_id=sid,
                        status="skipped",
                        reason="cooldown",
                        enqueued=0,
                        skipped=0,
                        errors=0,
                        duration_ms=0.0,
                        details=[],
                    )
                )
                continue

            t0 = time.perf_counter()
            try:
                max_n = max(0, int(source.max_per_run(ctx)))
                # Let the source read max from ctx/env; keep ctx stable.
                ctx.env.setdefault("QUENTIN_TASK_SOURCE_MAX_PER_RUN", str(max_n))
                res = source.run(ctx)
                if inspect.isawaitable(res):
                    report = await res  # type: ignore[assignment]
                else:
                    report = res  # type: ignore[assignment]
                dt_ms = (time.perf_counter() - t0) * 1000.0

                # Normalize: ensure bounded integer fields.
                report = TaskSourceRunReport(
                    source_id=report.source_id,
                    status=str(report.status or "ok"),
                    reason=str(report.reason or ""),
                    enqueued=int(report.enqueued),
                    skipped=int(report.skipped),
                    errors=int(report.errors),
                    duration_ms=float(report.duration_ms or dt_ms),
                    details=list(report.details or []),
                )
                source_reports.append(report)
                self._last_run_at[sid] = float(ctx.now_ts)
                total_enq += int(report.enqueued)
                total_skip += int(report.skipped)
                task_details.extend(list(report.details or []))
            except Exception as e:  # noqa: BLE001
                dt_ms = (time.perf_counter() - t0) * 1000.0
                source_reports.append(
                    TaskSourceRunReport(
                        source_id=sid,
                        status="error",
                        reason="error",
                        enqueued=0,
                        skipped=0,
                        errors=1,
                        duration_ms=float(dt_ms),
                        details=[{"error": repr(e)[:2000]}],
                    )
                )

        return CombinedTaskSourcesReport(
            enqueued=int(total_enq),
            skipped=int(total_skip),
            details=list(task_details),
            sources=list(source_reports),
        )

    def _ordered_sources(self) -> Sequence[TaskSource]:
        srcs = list(self._sources.values())
        srcs.sort(key=lambda s: (-int(getattr(s.spec, "priority", 0) or 0), str(s.spec.id)))
        return srcs

