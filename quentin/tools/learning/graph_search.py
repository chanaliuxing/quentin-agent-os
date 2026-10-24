from __future__ import annotations

import logging
import json
from typing import Dict, Any, List, Optional
from quentin.knowledge_graph.service import GraphService
from quentin.knowledge_graph.schema import NodeType, EdgeType
from quentin.tools.schemas import ToolCallRequest, ToolCallResult
from quentin.tools.manager import ToolCallContext

logger = logging.getLogger(__name__)

class GraphSearchTool:
    """
    Advanced Knowledge Graph Search Tool (Phase 4).
    Allows agents to traverse relations and explain provenances.
    """
    def __init__(self, service: Optional[GraphService] = None):
        self.service = service or GraphService()

    async def call(self, request: ToolCallRequest, ctx: ToolCallContext) -> ToolCallResult:
        method = request.payload.get("method", "get_neighbors")
        params = request.payload.get("params", {})

        try:
            if method == "get_neighbors":
                ref_id = params.get("ref_id")
                node_type = NodeType(params.get("node_type", "memory"))
                depth = int(params.get("depth", 1))
                
                node = self.service.store.get_node_by_ref(node_type, ref_id)
                if not node:
                    return ToolCallResult.fail(f"Node not found: {node_type}:{ref_id}")
                
                result = self.service.get_neighbors(node.node_id, depth=depth, direction="both")
                return ToolCallResult.success(result)

            elif method == "explain_link":
                src = (NodeType(params["src_type"]), params["src_id"])
                dst = (NodeType(params["dst_type"]), params["dst_id"])
                result = await self.service.explain_link(src, dst, use_llm=True)
                return ToolCallResult.success(result)

            elif method == "explain_provenance":
                ref_id = params.get("ref_id")
                node_type = NodeType(params.get("node_type", "memory"))
                result = self.service.explain_provenance(ref_id, node_type)
                return ToolCallResult.success(result)

            else:
                return ToolCallResult.fail(f"Unknown graph method: {method}")

        except Exception as e:
            logger.exception("GraphSearchTool failed")
            return ToolCallResult.fail(str(e))

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            "name": "graph_search",
            "description": "Query the Knowledge Graph for relations, provenance, and semantic links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["get_neighbors", "explain_link", "explain_provenance"],
                        "description": "The graph query method to use."
                    },
                    "params": {
                        "type": "object",
                        "properties": {
                            "ref_id": {"type": "string", "description": "The reference ID (e.g. memory_id or task_id)."},
                            "node_type": {"type": "string", "enum": ["memory", "trace", "skill", "goal", "concept"], "default": "memory"},
                            "depth": {"type": "integer", "default": 1},
                            "src_id": {"type": "string"},
                            "src_type": {"type": "string"},
                            "dst_id": {"type": "string"},
                            "dst_type": {"type": "string"}
                        }
                    }
                },
                "required": ["method", "params"]
            }
        }
