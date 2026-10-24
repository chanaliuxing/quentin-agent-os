# tests/integration/test_brain_daemon_maintenance.py

import pytest
import os
import json
import time
from pathlib import Path
from quentin.runtime.brain_daemon import BrainDaemon, BrainDaemonConfig
from quentin.runtime.task_queue import TaskQueue
from meta_agent.patches.store import PatchStore
from meta_agent.patchflow.queue import PatchQueue

def test_brain_daemon_maintenance_cycle(tmp_path):
    repo_root = tmp_path
    (repo_root / "blueprint").mkdir()
    (repo_root / "data").mkdir()
    
    # Create a dummy blueprint spec_v3.json
    spec = {
        "version": "3.0.0",
        "items": [
            {
                "id": "gap_daemon",
                "name": "Gap Daemon",
                "layer": "L1",
                "phase": "P1",
                "category": "core",
                "description": "Test gap",
                "hints": {"modules": ["quentin/mutable/gap_daemon.py"]}
            }
        ]
    }
    (repo_root / "blueprint" / "spec_v3.json").write_text(json.dumps(spec))
    
    # Set env vars
    os.environ["LLM_STUB"] = "1"
    os.environ["CODER_BACKEND"] = "deterministic"
    os.environ["QUENTIN_TASK_SOURCES_ENABLE"] = "1"
    os.environ["QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH"] = "1"
    os.environ["META_AGENT_PATCHFLOW_RUN"] = "1"
    os.environ["META_AGENT_PATCHFLOW_SYNC_STORE"] = "1"
    os.environ["QUENTIN_TASK_SOURCES_EVERY_SEC"] = "0.1"
    os.environ["QUENTIN_BRAIN_BLUEPRINT_AUTOPATCH_EVERY_SEC"] = "0.1"
    os.environ["QUENTIN_BRAIN_SLEEP"] = "0.1"
    
    config = BrainDaemonConfig(
        run_task_sources=True,
        run_blueprint_autopatch=True,
        run_patchflow=True,
        task_sources_every_sec=0.1,
        blueprint_autopatch_every_sec=0.1,
        sleep_seconds=0.1
    )
    
    old_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        daemon = BrainDaemon(config=config)
        
        # Run queue worker for a very short time in a separate thread or just mock the loop
        # Since run_queue_forever is a while True loop, we can mock claim_next to return None then raise StopIteration
        
        from unittest.mock import MagicMock, patch
        
        # We want to run it at least twice to trigger the intervals
        with patch.object(TaskQueue, "claim_next", side_effect=[None, None, Exception("StopLoop")]):
            try:
                daemon.run_queue_forever(worker_id="test-worker")
            except Exception as e:
                if str(e) != "StopLoop":
                    raise
        
        # Check if autopatch created a patch in PatchStore
        store = PatchStore()
        patches = store.list_patches()
        assert len(patches) >= 1
        
        # Check if patchflow synced it to PatchQueue
        pq = PatchQueue()
        queue_items = pq.load_all()
        assert len(queue_items) >= 1
        
    finally:
        os.chdir(old_cwd)
