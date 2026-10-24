from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_cognitive_loop_run_goal_uses_lane_orchestrator(monkeypatch) -> None:
    from quentin.cognitive.loop_impl import CognitiveLoop
    from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator

    called = {"lane_key": None}

    def _fake_run_sync(lane_key, coro_fn):
        called["lane_key"] = lane_key
        return asyncio.run(coro_fn())

    monkeypatch.setattr(lane_orchestrator, "run_sync", _fake_run_sync)

    class _DummyLoop:
        async def _run_goal_internal(self, task):
            return {"task_id": task.task_id, "ok": True}

    task = SimpleNamespace(task_id="task-1", metadata={"session_id": "session-abc"})
    result = CognitiveLoop.run_goal(_DummyLoop(), task)  # type: ignore[arg-type]

    assert called["lane_key"] == "session-abc"
    assert result["ok"] is True


def test_session_checkpoint_uses_dirty_sync(tmp_path, monkeypatch) -> None:
    from quentin.infra.sessions.checkpoint import SessionCheckpoint
    from quentin.infra.sessions.dirty_sync import dirty_sync

    touched = {"tracked": False, "synced": False}

    monkeypatch.setattr(dirty_sync, "track_change", lambda *_args, **_kwargs: touched.__setitem__("tracked", True))
    monkeypatch.setattr(dirty_sync, "should_sync", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dirty_sync, "mark_synced", lambda *_args, **_kwargs: touched.__setitem__("synced", True))

    cp = SessionCheckpoint(storage_dir=str(tmp_path))
    cp.save_checkpoint("task-x", {"context": {"k": "v"}})

    assert touched["tracked"] is True
    assert touched["synced"] is True
    assert (tmp_path / "task-x.checkpoint.json").exists()
