from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from quentin.cognitive.loop import CognitiveLoop
from quentin.runtime.system_events import SystemEventQueue


def test_run_self_programming_cycle_v2_help() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_self_programming_cycle_v2.py"
    assert script.exists()

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0


def test_system_event_relay_in_next_cognitive_iteration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M3_SYSTEM_EVENTS", "1")
    queue = SystemEventQueue(repo_root=tmp_path)
    queue.enqueue_event(
        session_id="global",
        event_type="self_programming_patch_applied",
        payload={
            "gap_id": "gap-smoke-1",
            "patch_id": "patch-smoke-1",
            "status": "applied",
            "message": "Patch passed sandbox tests and was applied.",
        },
        source="self_programming_engine_v2",
    )

    loop = CognitiveLoop(repo_root=str(tmp_path), system_event_queue=queue)
    first = loop._drain_system_events_for_planner(session_id="sess-smoke")
    second = loop._drain_system_events_for_planner(session_id="sess-smoke")

    assert "System events completed in background" in first
    assert "self_programming_patch_applied" in first
    assert "patch-smoke-1" in first
    assert second == ""
