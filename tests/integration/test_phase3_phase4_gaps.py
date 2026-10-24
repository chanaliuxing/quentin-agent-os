# tests/integration/test_phase3_phase4_gaps.py

import pytest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from quentin.skills.skill_loop import SkillLoopRunner, DoneCouncil
from quentin.knowledge_graph.service import GraphService, NodeType, EdgeType

@pytest.mark.asyncio
async def test_done_council_review(tmp_path):
    # Mock CouncilManager
    mock_council_mgr = MagicMock()
    # outcome.final_output.verdict
    mock_outcome = MagicMock()
    mock_outcome.final_output.verdict = "approve"
    mock_outcome.final_output.current_summary = "Good code"
    mock_council_mgr.run.return_value = mock_outcome
    
    dc = DoneCouncil(council=mock_council_mgr)
    
    skill_file = tmp_path / "test_skill.py"
    skill_file.write_text("def test_skill(): pass")
    
    result = dc.review_skill("test_skill", skill_file, {"candidate_id": "c1"})
    assert result["approved"] is True
    assert result["verdict"] == "approve"

@pytest.mark.asyncio
async def test_graph_api_new_capabilities(tmp_path):
    os.environ["QUENTIN_GRAPH_STORE"] = "file"
    os.environ["QUENTIN_GRAPH_FILE_PATH"] = str(tmp_path / "graph.json")
    
    gs = GraphService()
    
    # Create some nodes and links using valid NodeType members
    gs.create_link((NodeType.MEMORY, "m1"), (NodeType.CANDIDATE, "c1"), EdgeType.SIMILAR_TO)
    gs.create_link((NodeType.CANDIDATE, "c1"), (NodeType.SKILL, "s1"), EdgeType.PRODUCES_SKILL)
    
    # 1. Test get_neighbors with depth
    subgraph = gs.get_neighbors(gs.store.get_node_by_ref(NodeType.MEMORY, "m1").node_id, depth=2, direction="out")
    node_refs = [n["ref_id"] for n in subgraph["nodes"]]
    assert "c1" in node_refs
    assert "s1" in node_refs
    
    # 2. Test explain_link with use_llm=False
    explanation = await gs.explain_link((NodeType.MEMORY, "m1"), (NodeType.SKILL, "s1"), use_llm=False)
    assert "path" in explanation
    assert len(explanation["path"]) == 2
    assert "m1" in explanation["summary"]
    assert "s1" in explanation["summary"]
    
    # 3. Test GraphML export
    graphml = gs.export_subgraph((NodeType.MEMORY, "m1"), depth=2, format="graphml")
    assert "<?xml" in graphml
    assert "<graphml" in graphml
    assert "m1" in graphml
    assert "s1" in graphml

@pytest.mark.asyncio
async def test_skill_loop_full_cycle_integration(tmp_path):
    # This test ensures that when SkillLoopRunner runs, it goes through DoneCouncil and Registrar (MTS + Graph)
    os.environ["QUENTIN_GRAPH_STORE"] = "file"
    os.environ["QUENTIN_GRAPH_FILE_PATH"] = str(tmp_path / "graph_loop.json")
    
    cid = "cand_123"
    skill_name = f"skill_{cid}"
    skill_path = Path(f"quentin/mutable/skills/{skill_name}.py")
    
    with (
        patch("quentin.skills.candidate_store.CandidateStore.get_pending") as mock_get_pending,
        patch("quentin.skills.candidate_store.CandidateStore.mark_processed") as mock_mark,
        patch("meta_agent.self_programming.engine_v2.SelfProgrammingEngineV2.run_for_gaps") as mock_engine,
        patch("quentin.skills.skill_loop.DoneCouncil.review_skill") as mock_review,
        patch("quentin.skills.registrar.SkillRegistrar.register", wraps=SkillRegistrar().register) as mock_reg,
        patch("quentin.memory.fabric.MemoryFabric.remember_atomic") as mock_remember
    ):
        mock_get_pending.return_value = [{"candidate_id": cid, "description": "test", "tags": []}]
        mock_review.return_value = {"approved": True, "verdict": "approve"}
        
        # Simulate file being created by engine
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text("def test(): pass")
        
        runner = SkillLoopRunner()
        runner.run_once()
        
        assert mock_review.called
        assert mock_reg.called
        # Check if MTS memory was recorded (Phase 3)
        assert mock_remember.called
        args, kwargs = mock_remember.call_args
        assert kwargs.get("tier") == MemoryTier.MTS
        
        # Check if graph was synced (Phase 4)
        gs = runner.graph_service
        node = gs.store.get_node_by_ref(NodeType.SKILL, skill_name)
        assert node is not None
        
        # Cleanup
        if skill_path.exists():
            skill_path.unlink()

from quentin.skills.registrar import SkillRegistrar
from quentin.memory.models import MemoryTier