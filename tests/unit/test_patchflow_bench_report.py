# tests/unit/test_patchflow_bench_report.py

import pytest
import os
import json
from unittest.mock import MagicMock, patch
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator, PatchFlowConfig
from meta_agent.patchflow.models import PatchProposal

def test_patchflow_run_bench(tmp_path):
    os.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    
    config = PatchFlowConfig(
        run_bench=True,
        bench_cmd="echo bench_ran",
        environment="sandbox",
        auto_apply=False
    )
    
    orchestrator = PatchFlowOrchestrator(config=config)
    
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
    
    with patch("meta_agent.safety.checker.PatchSafetyChecker.check") as mock_safety:
        mock_safety.return_value = MagicMock(allow_apply=True, requires_human_review=False, reasons=[])
        
        orchestrator._process_single(proposal)
        
        assert "bench" in proposal.metadata
        assert proposal.metadata["bench"]["ok"] is True
        assert "bench_ran" in proposal.metadata["bench"]["stdout_preview"]

def test_patchflow_persist_report(tmp_path):
    os.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    
    orchestrator = PatchFlowOrchestrator()
    
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
    proposal.status = "approved"
    proposal.metadata["safety"] = {"allow_apply": True}
    
    orchestrator._persist_report(proposal)
    
    report_path = tmp_path / "data" / "patchflow_reports" / f"{proposal.id}.json"
    assert report_path.exists()
    
    with report_path.open("r") as f:
        report = json.load(f)
        assert report["patchflow_id"] == proposal.id
        assert report["status"] == "approved"
