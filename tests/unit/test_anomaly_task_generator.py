import pytest

from quentin.observability.anomaly_detector import AnomalyTaskGenerator
from quentin.runtime.task_queue import TaskQueue


class _FakeObs:
    def __init__(self, overview):
        self._overview = overview

    async def get_overview(self):
        return self._overview


@pytest.mark.asyncio
async def test_anomaly_task_generator_enqueues_lease_and_deadletter_remediations(tmp_path):
    overview = {
        "domain": {"task": {"by_domain_env": []}, "actions": {"by_domain_env_action": []}},
        "memory": {"events": {"recall": {"avg_latency_ms": 1.0}}},
        "patches": {"by_status": {}},
        "tools": {"by_tool": []},
        "communication": {
            "leases": {
                "expired_count": 1,
                "expiring_soon_count": 4,
                "contention_events_recent": 4,
                "fencing_conflicts_recent": 3,
            },
            "dead_letters": {
                "trend": {
                    "recent_count": 7,
                    "previous_count": 2,
                    "growth_ratio": 3.5,
                }
            },
        },
    }
    queue = TaskQueue(repo_root=str(tmp_path))
    gen = AnomalyTaskGenerator(obs_service=_FakeObs(overview), task_queue=queue)
    task_ids = await gen.check_and_generate()
    assert task_ids
    items = queue.load_all()
    kinds = [str(it.metadata.get("anomaly_kind") or "") for it in items]
    assert "lease_renew_drift" in kinds
    assert "lease_fencing_conflict_spike" in kinds
    assert "dead_letter_growth_trend" in kinds
