
import pytest
from unittest.mock import MagicMock, AsyncMock
from quentin.knowledge_graph.service import GraphService
from quentin.knowledge_graph.schema import NodeType

@pytest.mark.asyncio
async def test_graph_query_by_intent():
    store = MagicMock()
    service = GraphService(store=store)
    
    # Mock LLM response
    from meta_agent.runtime import council
    council.ask_json = AsyncMock(return_value={
        "candidates": [
            {"ref_id": "tool_manager", "type": "concept", "reason": "Relevant to architecture"}
        ]
    })
    
    # Mock node lookup
    mock_node = MagicMock(node_id="n1", ref_id="tool_manager", title="Tool Manager", node_type=NodeType.CONCEPT)
    store.get_node_by_ref.return_value = mock_node
    
    # Mock neighbor lookup
    store.get_neighbors.return_value = []
    
    res = await service.query_by_intent("How does the system manage tools?")
    
    assert res["intent"] == "How does the system manage tools?"
    assert len(res["results"]) > 0
    assert res["results"][0]["node"]["ref_id"] == "tool_manager"
    assert "context" in res["results"][0]
