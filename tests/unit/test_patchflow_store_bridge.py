from __future__ import annotations

import os
from pathlib import Path

from meta_agent.patches.models import PatchProposal as CodePatchProposal
from meta_agent.patches.store import PatchStore
from meta_agent.patchflow.queue import PatchQueue
from meta_agent.patchflow.store_bridge import sync_patch_store_to_patch_queue


def test_sync_patch_store_to_patch_queue_enqueues_once(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "patches.json"
    queue_path = tmp_path / "patch_queue.jsonl"
    monkeypatch.setenv("META_AGENT_PATCH_STORE_PATH", str(store_path))
    monkeypatch.setenv("META_AGENT_PATCH_QUEUE_PATH", str(queue_path))

    store = PatchStore(path=str(store_path))
    patch = CodePatchProposal(
        id="p1",
        target_files=["a.py"],
        diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n+print('x')\n",
        intent="test",
        status="proposed",
        metadata={"gap_id": "cap.x"},
    )
    store.save_patch(patch)

    out1 = sync_patch_store_to_patch_queue(patch_store=store, patch_queue=PatchQueue(path=str(queue_path)), max_to_enqueue=10)
    assert out1["enqueued"] == 1
    assert queue_path.exists()

    out2 = sync_patch_store_to_patch_queue(patch_store=store, patch_queue=PatchQueue(path=str(queue_path)), max_to_enqueue=10)
    assert out2["enqueued"] == 0

