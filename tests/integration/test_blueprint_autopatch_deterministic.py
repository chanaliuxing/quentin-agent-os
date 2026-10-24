# tests/integration/test_blueprint_autopatch_deterministic.py

import pytest
import os
import json
import shutil
from pathlib import Path
from quentin.blueprint.auto_patcher import BlueprintGapAutoPatcher
from meta_agent.patches.store import PatchStore

def test_blueprint_autopatch_deterministic(tmp_path):
    repo_root = tmp_path
    (repo_root / "blueprint").mkdir()
    (repo_root / "data").mkdir()
    
    # Create a dummy blueprint spec_v3.json
    spec = {
        "version": "3.0.0",
        "items": [
            {
                "id": "gap_1",
                "name": "Gap 1",
                "layer": "L1",
                "phase": "P1",
                "category": "core",
                "description": "Test gap",
                "hints": {"modules": ["quentin/mutable/gap_1.py"]}
            }
        ]
    }
    (repo_root / "blueprint" / "spec_v3.json").write_text(json.dumps(spec))
    
    # Set env vars for deterministic run
    os.environ["CODER_BACKEND"] = "deterministic"
    os.environ["LLM_STUB"] = "1"
    os.environ["SELFPROG_FAST_DETERMINISTIC"] = "0" # We want it to run, not skip
    
    # Change CWD to repo_root for the test
    old_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        patcher = BlueprintGapAutoPatcher(blueprint_path="blueprint/spec_v3.json")
        report = patcher.propose_patches_for_gaps(run_selfprog=True)
        
        assert report.selfprog_ran is True
        assert report.proposed >= 1
        
        # Check PatchStore
        store = PatchStore()
        patches = store.list_patches()
        assert len(patches) >= 1
        assert any((p.metadata or {}).get("gap_id") == "gap_1" for p in patches)
        
    finally:
        os.chdir(old_cwd)
