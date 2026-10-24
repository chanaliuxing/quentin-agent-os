from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.runtime.cron_runner import CronRunner, CronRunnerConfig
from quentin.tools.execution_parity import cron_tool
from quentin.tools.execution_parity import nodes_tool


def _ctx(root: Path):
    return SimpleNamespace(metadata={"repo_root": str(root)})


def test_cron_runner_run_once_enqueues_due_tasks(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = cron_tool(
        {
            "action": "schedule",
            "name": "runner_due",
            "task_input": "runner hello",
            "interval": "1s",
            "domain": "maintenance",
            "environment": "sandbox",
        },
        ctx,
    )
    assert out["status"] == "ok"
    runner = CronRunner(CronRunnerConfig(repo_root=str(tmp_path), tick_seconds=0.2, max_tasks_per_tick=5))
    res = runner.run_once()
    assert res["status"] == "ok"
    qf = tmp_path / "data" / "tasks" / "queue.jsonl"
    assert qf.exists()
    assert "runner hello" in qf.read_text(encoding="utf-8")


def test_cron_runner_reconciles_and_auto_assigns(tmp_path: Path) -> None:
    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    ctx = _ctx(tmp_path)
    nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    q = TaskQueue(repo_root=str(tmp_path))
    item = TaskQueueItem.new(input_text="pending x", domain="maintenance", environment="sandbox")
    q.append(item)
    runner = CronRunner(
        CronRunnerConfig(
            repo_root=str(tmp_path),
            tick_seconds=0.2,
            max_tasks_per_tick=5,
            reconcile_assignments=True,
            auto_assign_pending=True,
        )
    )
    res = runner.run_once()
    assert res["status"] == "ok"
    rec = res.get("assignment_reconcile") or {}
    assert rec.get("status") == "ok"
    listed = nodes_tool({"action": "list_assignments"}, ctx)
    assert any(str(a.get("task_id") or "") == item.task_id for a in listed.get("assignments") or [])
