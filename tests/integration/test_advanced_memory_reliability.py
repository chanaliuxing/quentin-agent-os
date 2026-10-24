# tests/integration/test_advanced_memory_reliability.py

import pytest
import os
import json
import shutil
import asyncio
from pathlib import Path
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier
from unittest.mock import patch, MagicMock

def test_hybrid_score_normalization(tmp_path):
    # Use SqliteMemoryStore for testing
    db_path = tmp_path / "test_memory.db"
    os.environ["QUENTIN_MEMORY_FTS"] = "1"
    
    fabric = MemoryFabric(db_path=str(db_path))
    
    # 1. Add some records
    fabric.remember_atomic(
        content="UniqueTokenXYZ: This is a very specific piece of information about a secret project.",
        source="test",
        tier=MemoryTier.STS,
        kind="episodic",
        importance=0.9
    )
    fabric.remember_atomic(
        content="Generic info: This is common knowledge about general things.",
        source="test",
        tier=MemoryTier.STS,
        kind="episodic",
        importance=0.5
    )
    
    # 2. Test hybrid recall with specific token
    # The unique token should rank the first record very high in text score
    query = MemoryQuery(
        text="UniqueTokenXYZ",
        mode="hybrid",
        alpha=0.5, # 50% vector, 50% text
        top_k=5,
        text_mode="fts"
    )
    
    results = fabric.recall(query)
    assert len(results) >= 1
    assert "UniqueTokenXYZ" in results[0].content

def test_markdown_memory_export(tmp_path):
    db_path = tmp_path / "test_export.db"
    export_dir = tmp_path / "export"
    
    # Explicitly use Sqlite for this test to avoid Postgres env issues
    os.environ["QUENTIN_MEMORY_STORE"] = "sqlite"
    fabric = MemoryFabric(db_path=str(db_path))
    fabric.remember_atomic(content="MTS Record", source="test", tier=MemoryTier.MTS)
    fabric.remember_atomic(content="STS Record", source="test", tier=MemoryTier.STS)
    
    res = fabric.export_to_markdown(output_dir=str(export_dir))
    assert res["status"] == "ok"
    
    # MemoryTier.value is 'short_term', 'mid_term', 'long_term'
    assert (export_dir / "short_term.md").exists()
    assert (export_dir / "mid_term.md").exists()
    
    sts_content = (export_dir / "short_term.md").read_text()
    assert "STS Record" in sts_content
    assert "MTS Record" not in sts_content

@pytest.mark.asyncio
async def test_context_flush_logic_in_loop(tmp_path):
    # Mock context window to be very small to trigger flush
    with patch("quentin.llm.context_budget.get_context_window_limit") as mock_limit:
        mock_limit.return_value = 1000
        
        from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask
        
        # Use Sqlite
        os.environ["QUENTIN_MEMORY_STORE"] = "sqlite"
        fabric = MemoryFabric(db_path=str(tmp_path / "loop_memory.db"))
        loop = CognitiveLoop(repo_root=str(tmp_path), memory_fabric=fabric)
        
        # Mock planner and executor
        mock_planner = MagicMock()
        mock_planner.return_value = {"steps": []}
        loop._planner = mock_planner
        
        mock_executor = MagicMock()
        # High cost tokens in result
        mock_executor.return_value = {
            "final_output": "done", 
            "raw": {"success": True, "meta": {"tokens_used": 900}}
        }
        loop._executor = mock_executor
        
        # Mock council for memory_flush
        with patch.object(loop.council_manager, "run_council") as mock_run:
            mock_decision = MagicMock()
            mock_decision.final = {"answer": {"summary": "Session summary", "tags": ["tag1"]}}
            mock_run.return_value = mock_decision
            
            task = CognitiveTask(input_text="Trigger flush")
            
            # Mock DoneCheck to fail first then succeed
            from quentin.goals.done_definition import DoneCheckResult
            mock_done = DoneCheckResult(is_done=False, confidence=0.5, reasons=["not yet"])
            mock_done_success = DoneCheckResult(is_done=True, confidence=1.0, reasons=["done"])
            
            loop.goal_manager.check_done_and_record = MagicMock(side_effect=[mock_done, mock_done_success])
            
            # Call _run_goal_internal directly because we are already in an event loop
            await loop._run_goal_internal(task)
            
            # Verify flush was called
            assert mock_run.called
            # Check memory for flush record
            recs = fabric.recall(MemoryQuery(text="Memory Flush", top_k=1))
            assert len(recs) > 0
            assert "Session summary" in recs[0].content
