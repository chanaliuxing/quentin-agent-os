from __future__ import annotations

import os
from pathlib import Path
import json

from meta_agent.patches.models import PatchProposal as CodePatchProposal
from meta_agent.patches.store import PatchStore
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator


def test_patchflow_run_cycle_syncs_patch_store_to_queue(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "patches.json"
    queue_path = tmp_path / "patch_queue.jsonl"
    monkeypatch.setenv("META_AGENT_PATCH_STORE_PATH", str(store_path))
    monkeypatch.setenv("META_AGENT_PATCH_QUEUE_PATH", str(queue_path))
    monkeypatch.setenv("META_AGENT_PATCHFLOW_SYNC_STORE", "1")
    monkeypatch.setenv("META_AGENT_PATCHFLOW_SYNC_STORE_MAX", "5")

    store = PatchStore(path=str(store_path))
    store.save_patch(
        CodePatchProposal(
            id="p1",
            target_files=["quentin/mutable/toy_planner.py"],
            diff="diff --git a/quentin/mutable/toy_planner.py b/quentin/mutable/toy_planner.py\n",
            intent="test",
            status="proposed",
            metadata={"gap_id": "cap.x"},
        )
    )

    orch = PatchFlowOrchestrator()
    out = orch.run_cycle()
    assert int(out.get("processed") or 0) >= 1
    assert queue_path.exists()
    # Ensure queue entries are no longer pending after processing.
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert lines
    obj = json.loads(lines[0])
    assert obj.get("status") in ("approved", "needs_review", "blocked", "rejected", "rolled_back", "applied")

