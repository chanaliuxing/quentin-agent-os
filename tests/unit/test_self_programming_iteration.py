from datetime import datetime, timedelta
from typing import List

from meta_agent.self_programming.evolution_loop import run_once
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.schema import ProgrammingTask
from meta_agent.self_programming.strategy import SimpleEvolutionStrategyManager


def _sample_task(task_id: str = "task-1") -> ProgrammingTask:
    return ProgrammingTask(
        task_id=task_id,
        origin="bugfix",
        description="Fix failing tests",
        repo_root=".",
        related_files=[],
        context_summary="",
        constraints={},
        acceptance_criteria=[],
    )


def test_jsonl_metrics_store_roundtrip(tmp_path) -> None:
    store = JsonlMetricsStore(repo_root=tmp_path)
    now = datetime.utcnow()
    older = now - timedelta(hours=1)

    store.log_run(
        {
            "task_id": "t1",
            "status": "approved",
            "timestamp": older,
            "commit_hash": "abc",
            "branch_name": "main",
            "raw_test_output": "ok",
            "metrics": {"tests_total": 1},
            "task_payload": {},
        }
    )
    store.log_run(
        {
            "task_id": "t2",
            "status": "approved",
            "timestamp": now,
            "commit_hash": "def",
            "branch_name": "main",
            "raw_test_output": "ok",
            "metrics": {"tests_total": 2},
            "task_payload": {},
        }
    )

    runs = store.get_runs_by_status("approved", limit=5)
    assert len(runs) == 2
    assert runs[0]["task_id"] == "t2"
    assert runs[1]["task_id"] == "t1"


def test_strategy_generates_retry_task(tmp_path) -> None:
    store = JsonlMetricsStore(repo_root=tmp_path)
    store.log_run(
        {
            "task_id": "bug-123",
            "status": "test_fail",
            "timestamp": datetime.utcnow(),
            "commit_hash": None,
            "branch_name": None,
            "raw_test_output": "AssertionError: boom",
            "metrics": {},
            "task_payload": _sample_task("bug-123").__dict__,
        }
    )
    strategy = SimpleEvolutionStrategyManager(metrics_store=store)

    tasks = strategy.generate_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_id == "retry_of_bug-123"
    assert "AssertionError" in task.description


def test_run_once_executes_tasks() -> None:
    calls: List[str] = []

    class DummyStrategy:
        def generate_tasks(self) -> List[ProgrammingTask]:
            return [_sample_task("abc"), _sample_task("def")]

    class DummyEngine:
        def run_task(self, task: ProgrammingTask) -> None:
            calls.append(task.task_id)

    attempted = run_once(DummyStrategy(), DummyEngine())  # type: ignore[arg-type]
    assert attempted == 2
    assert calls == ["abc", "def"]
