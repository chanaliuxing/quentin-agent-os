# tests/integration/test_patchflow_report_generation.py

import pytest
import os
import json
from pathlib import Path
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator, PatchFlowConfig
from meta_agent.patchflow.models import PatchProposal
from meta_agent.patchflow.queue import PatchQueue

def test_patchflow_cycle_report_generation(tmp_path):
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    
    # Configure PatchFlow
    config = PatchFlowConfig(
        auto_apply=False,
        run_tests=False,
        environment="sandbox"
    )
    
    # Create a proposal in the queue
    queue_path = repo_root / "data" / "patch_queue.jsonl"
    queue = PatchQueue(path=str(queue_path))
    
    proposal = PatchProposal.new(
        source="test",
        kind="code",
        patch_format="raw_text",
        targets=["test.py"],
        body={"raw": "print(1)"},
        intent="test",
        reason="test",
        blueprint_context=""
    )
    queue.append(proposal)
    
    # Run orchestrator
    old_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        orchestrator = PatchFlowOrchestrator(queue=queue, config=config)
        # Mock safety checker to allow apply
        with (
            patch("meta_agent.safety.checker.PatchSafetyChecker.check") as mock_safety,
            patch("meta_agent.patchflow.orchestrator.sync_patch_store_to_patch_queue")
        ):
            mock_safety.return_value = MagicMock(allow_apply=True, requires_human_review=False, reasons=[])
            
            orchestrator.run_cycle()
            
            # Check report
            report_dir = repo_root / "data" / "patchflow_reports"
            assert report_dir.exists()
            
            report_files = list(report_dir.glob("*.json"))
            assert len(report_files) >= 1
            
            with report_files[0].open("r") as f:
                report = json.load(f)
                assert "patchflow_id" in report
                assert report["status"] == "approved"
    finally:
        os.chdir(old_cwd)

from unittest.mock import MagicMock, patch
