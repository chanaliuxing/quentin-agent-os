from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import pytest

from quentin.runtime.task_source_registry import (
    TaskSourceContext,
    TaskSourceRegistry,
    TaskSourceRunReport,
    TaskSourceSpec,
)


@dataclass
class _FakeQueue:
    repo_root: str


class _FakeSource:
    def __init__(self, *, sid: str, priority: int, enabled: bool = True, cooldown: float = 0.0) -> None:
        self._spec = TaskSourceSpec(
            id=sid,
            name=sid,
            kind="test",
            priority=priority,
            default_enabled=True,
            max_per_run=10,
            cooldown_sec=cooldown,
        )
        self._enabled = enabled
        self.runs = 0

    @property
    def spec(self) -> TaskSourceSpec:
        return self._spec

    def enabled(self, ctx: TaskSourceContext) -> bool:
        return bool(self._enabled)

    def max_per_run(self, ctx: TaskSourceContext) -> int:
        return int(self._spec.max_per_run)

    async def run(self, ctx: TaskSourceContext) -> TaskSourceRunReport:
        self.runs += 1
        return TaskSourceRunReport(source_id=self.spec.id, status="ok", reason="ok", enqueued=1, skipped=0, errors=0, duration_ms=0.0, details=[])


@pytest.mark.asyncio
async def test_registry_orders_by_priority(tmp_path: Path) -> None:
    reg = TaskSourceRegistry()
    a = _FakeSource(sid="a", priority=10)
    b = _FakeSource(sid="b", priority=100)
    reg.register(a)
    reg.register(b)

    ctx = TaskSourceContext(
        repo_root=tmp_path,
        queue=_FakeQueue(repo_root=str(tmp_path)),
        domain="core",
        environment="sandbox",
        session_id="t",
        now_ts=time.time(),
        env={},
    )
    report = await reg.run_enabled(ctx)
    assert [s.source_id for s in report.sources] == ["b", "a"]
    assert a.runs == 1
    assert b.runs == 1


@pytest.mark.asyncio
async def test_registry_respects_disabled_sources(tmp_path: Path) -> None:
    reg = TaskSourceRegistry()
    s = _FakeSource(sid="x", priority=0, enabled=False)
    reg.register(s)

    ctx = TaskSourceContext(repo_root=tmp_path, queue=_FakeQueue(repo_root=str(tmp_path)), domain="d", environment="e", session_id="s", env={})
    report = await reg.run_enabled(ctx)
    assert report.enqueued == 0
    assert report.sources[0].status == "skipped"
    assert report.sources[0].reason == "disabled"
    assert s.runs == 0


@pytest.mark.asyncio
async def test_registry_enforces_cooldown(tmp_path: Path) -> None:
    reg = TaskSourceRegistry()
    s = _FakeSource(sid="c", priority=0, enabled=True, cooldown=60.0)
    reg.register(s)

    ctx = TaskSourceContext(
        repo_root=tmp_path,
        queue=_FakeQueue(repo_root=str(tmp_path)),
        domain="d",
        environment="e",
        session_id="s",
        now_ts=1000.0,
        env={},
    )
    r1 = await reg.run_enabled(ctx)
    assert r1.enqueued == 1
    assert s.runs == 1

    # Same timestamp -> within cooldown window.
    r2 = await reg.run_enabled(ctx)
    assert r2.enqueued == 0
    assert r2.sources[0].reason == "cooldown"
    assert s.runs == 1

