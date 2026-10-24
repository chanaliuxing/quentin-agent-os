from __future__ import annotations

from quentin.self_improvement.manager import SelfImprovementManager
from quentin.self_improvement.schemas import ImprovementTask


def test_self_improvement_manager_upsert_and_get(tmp_path):
    path = tmp_path / "improvement_tasks.json"
    mgr = SelfImprovementManager(path=path)

    t = ImprovementTask(
        task_id="t1",
        capability="memory_fabric",
        requirement_id=None,
        overall_status="implemented",
        title="do",
        description="d",
        priority=1,
        status="pending",
        meta={},
    )
    mgr.upsert_task(t)

    out = mgr.get_task("t1")
    assert out is not None
    assert out.task_id == "t1"
