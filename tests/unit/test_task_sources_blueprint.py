from __future__ import annotations

from dataclasses import dataclass

from quentin.runtime.task_queue import TaskQueue
from quentin.runtime.task_sources import enqueue_blueprint_gap_tasks, enqueue_patchflow_backlog_tasks


@dataclass
class _Spec:
    id: str
    name: str = ""
    layer: str = "L1"
    phase: str = "P0"


@dataclass
class _Status:
    spec: _Spec
    file_implemented: bool
    has_traces: bool
    has_experiments: bool
    score: float


@dataclass
class _Report:
    items: list[_Status]


class _FakeTracker:
    def __init__(self, report: _Report) -> None:
        self._report = report

    def scan(self) -> _Report:
        return self._report


def test_enqueue_blueprint_gap_tasks_dedupes_by_capability_id(tmp_path) -> None:
    q = TaskQueue(repo_root=tmp_path, path="queue.jsonl")

    report = _Report(
        items=[
            _Status(_Spec(id="cap.a", name="A"), file_implemented=False, has_traces=False, has_experiments=False, score=0.0),
            _Status(_Spec(id="cap.b", name="B"), file_implemented=True, has_traces=False, has_experiments=False, score=0.33),
        ]
    )
    tracker = _FakeTracker(report)

    r1 = enqueue_blueprint_gap_tasks(queue=q, tracker=tracker, limit=10)
    assert r1.enqueued == 2

    r2 = enqueue_blueprint_gap_tasks(queue=q, tracker=tracker, limit=10)
    assert r2.enqueued == 0
    assert r2.skipped >= 2


def test_enqueue_patchflow_backlog_tasks_dedupes_by_patch_id(tmp_path, monkeypatch) -> None:
    q = TaskQueue(repo_root=tmp_path, path="queue.jsonl")

    class _P:
        def __init__(self, pid: str, status: str):
            self.id = pid
            self.status = status
            self.created_at = "2026-02-08T00:00:00"
            self.source = "test"
            self.intent = "x"

    class _PQ:
        def load_all(self):
            return [_P("patch-1", "needs_review"), _P("patch-2", "blocked")]

    monkeypatch.setattr("quentin.runtime.task_sources.PatchQueue", lambda: _PQ())

    r1 = enqueue_patchflow_backlog_tasks(queue=q, limit=10)
    assert r1.enqueued == 2

    r2 = enqueue_patchflow_backlog_tasks(queue=q, limit=10)
    assert r2.enqueued == 0
