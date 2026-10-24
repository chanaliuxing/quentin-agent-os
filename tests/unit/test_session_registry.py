from __future__ import annotations

from pathlib import Path

from quentin.infra.concurrency.session_registry import SessionRegistry


def test_session_registry_acquire_release(tmp_path: Path) -> None:
    reg = SessionRegistry(repo_root=tmp_path)
    assert reg.acquire("sess/1", worker_id="w1") is True
    assert reg.acquire("sess/1", worker_id="w2") is False
    reg.release("sess/1", worker_id="w2")  # wrong owner
    assert reg.is_active("sess/1") is True
    reg.release("sess/1", worker_id="w1")
    assert reg.is_active("sess/1") is False

