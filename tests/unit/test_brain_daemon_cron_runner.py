from __future__ import annotations

from types import SimpleNamespace

from quentin.runtime.brain_daemon import BrainDaemon, BrainDaemonConfig


class _DummyLoop:
    def run_task(self, task):  # type: ignore[no-untyped-def]
        _ = task
        return SimpleNamespace(
            task_id="t1",
            goal_id="g1",
            done=False,
            done_confidence=0.0,
            final_output="ok",
            self_awareness={},
        )


class _DummySleep:
    def run_once(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


class _DummyImmune:
    def process_trace(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


class _FakeCronRunner:
    def __init__(self):
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return {"status": "ok", "enqueued_count": 0}


def _container() -> object:
    return SimpleNamespace(
        cognitive_loop=_DummyLoop(),
        sleep_loop=_DummySleep(),
        immune_loop=_DummyImmune(),
        settings=SimpleNamespace(repo_root="."),
    )


def test_brain_daemon_runs_cron_runner_if_due(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False, run_cron_runner=True, cron_runner_every_sec=0.1),
        container=_container(),  # type: ignore[arg-type]
    )
    fake = _FakeCronRunner()
    daemon.cron_runner = fake  # type: ignore[assignment]
    daemon._last_cron_runner_at = 0.0
    daemon._run_cron_runner_if_due(now=10.0)
    assert fake.calls == 1
    daemon._run_cron_runner_if_due(now=10.01)
    assert fake.calls == 1
    daemon._run_cron_runner_if_due(now=10.21)
    assert fake.calls == 2
