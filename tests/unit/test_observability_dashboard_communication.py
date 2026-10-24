import json
from pathlib import Path

from quentin.observability.dashboard import ObservabilityDashboard


class _FakeStore:
    def search(self, query):
        _ = query
        return []


class _FakeMemoryFabric:
    def __init__(self):
        self.store = _FakeStore()


def test_dashboard_collects_communication_metrics(tmp_path: Path, monkeypatch) -> None:
    class _LM:
        def status(self, platform=None):
            _ = platform
            return {
                "status": "ok",
                "count": 1,
                "listeners": [
                    {"platform": "discord", "status": "running", "restart_count": 2, "dropped_count": 3}
                ],
            }

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())

    ls = tmp_path / "data" / "channels" / "listener_state.json"
    ls.parent.mkdir(parents=True, exist_ok=True)
    ls.write_text(json.dumps({"seen": {}, "dead_letters": [{"platform": "discord"}]}, ensure_ascii=False), encoding="utf-8")

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
        ),
        encoding="utf-8",
    )

    dash = ObservabilityDashboard(memory_fabric=_FakeMemoryFabric(), repo_root=tmp_path)
    m = dash.collect_metrics()
    assert m.listener_count == 1
    assert m.listener_restart_total == 2
    assert m.listener_dropped_total == 3
    assert m.listener_dead_letter_total == 1
    assert m.canvas_ack_pending_count >= 1
