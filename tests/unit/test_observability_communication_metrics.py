import asyncio
import json
import time
from pathlib import Path

from quentin.observability.service import ObservabilityService


def test_observability_communication_metrics(tmp_path: Path, monkeypatch) -> None:
    now = time.time()
    class _LM:
        def status(self, platform=None):
            _ = platform
            return {
                "status": "ok",
                "count": 2,
                "listeners": [
                    {
                        "platform": "discord",
                        "status": "running",
                        "restart_count": 3,
                        "dropped_count": 2,
                        "last_restart_reason": "rate_limit",
                        "restart_reasons": {"rate_limit": 2, "network_error": 1},
                        "backoff_profile": "exponential",
                        "rate_limit_per_min": 60,
                    },
                    {
                        "platform": "slack",
                        "status": "running",
                        "restart_count": 1,
                        "dropped_count": 0,
                        "last_restart_reason": "auth_error",
                        "restart_reasons": {"auth_error": 1},
                        "backoff_profile": "linear",
                        "rate_limit_per_min": 45,
                    },
                ],
            }

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())

    ls = tmp_path / "data" / "channels" / "listener_state.json"
    ls.parent.mkdir(parents=True, exist_ok=True)
    ls.write_text(
        json.dumps(
            {
                "seen": {},
                "dead_letters": [
                    {"platform": "discord", "error": "x", "ts": now - 10},
                    {"platform": "discord", "error": "y", "ts": now - 20},
                    {"platform": "slack", "error": "z", "ts": now - 30},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    canvas = tmp_path / "data" / "canvas_components.json"
    canvas.parent.mkdir(parents=True, exist_ok=True)
    canvas.write_text(
        json.dumps(
            {
                "components": {
                    "c1": {"component_id": "c1", "status": "running", "updated_at": 1},
                    "c2": {"component_id": "c2", "status": "done", "updated_at": 1},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lease_file = tmp_path / "data" / "nodes_leases.json"
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(
        json.dumps(
            {
                "leases": {
                    "leader::g1": {
                        "lease_key": "leader::g1",
                        "group_key": "g1",
                        "node_id": "n2",
                        "epoch": 7,
                        "expires_at": now + 10,
                        "lease_ttl_sec": 30,
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    lev = tmp_path / "data" / "metrics" / "lease_events.jsonl"
    lev.parent.mkdir(parents=True, exist_ok=True)
    lev.write_text(
        json.dumps({"ts": now - 5, "kind": "fencing_conflict"}, ensure_ascii=False) + "\n"
        + json.dumps({"ts": now - 4, "kind": "leader_blocked_higher_priority"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    svc = ObservabilityService(runtime=None, repo_root=tmp_path)
    overview = asyncio.run(svc.get_overview())
    comm = overview["communication"]

    listeners = comm["listeners"]
    assert listeners["count"] == 2
    assert listeners["restart_total"] == 4
    assert listeners["dropped_total"] == 2
    assert int(listeners["restart_reasons"]["rate_limit"]) == 2
    assert int(listeners["restart_reasons"]["auth_error"]) == 1

    dead = comm["dead_letters"]
    assert dead["total"] == 3
    assert dead["by_platform"]["discord"] == 2
    assert dead["by_platform"]["slack"] == 1
    assert "trend" in dead

    canvas_hs = comm["canvas_handshake"]
    assert canvas_hs["active_components"] == 1
    assert canvas_hs["ack_pending"] >= 1

    leases = comm["leases"]
    assert leases["total"] == 1
    assert leases["leader_epoch_max"] == 7
    assert leases["fencing_conflicts_recent"] >= 1
    assert leases["contention_events_recent"] >= 1
