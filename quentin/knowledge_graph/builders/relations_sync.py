# quentin/knowledge_graph/builders/relations_sync.py
from __future__ import annotations
import logging
from typing import Dict, Any
from ..schema import NodeType, EdgeType
from ..service import GraphService

logger = logging.getLogger(__name__)

class RelationsSyncBuilder:
    """
    Parses the 'relations' dict from MemoryRecord and syncs to Graph.
    Expected relations format: {"crystallized_from:mem_id_123": 1.0}
    """
    def __init__(self, service: GraphService):
        self.service = service

    def sync_memory_relations(self, memory_id: str, relations: Dict[str, float], memory_title: str = ""):
        if not relations:
            return

        # Ensure source node exists
        self.service.sync_node(NodeType.MEMORY, memory_id, title=memory_title)

        for key, weight in relations.items():
            try:
                # Key format: "relation_type:target_id"
                if ":" not in key: 
                    continue
                    
                rel_type_str, target_id = key.split(":", 1)
                
                # Map string to EdgeType enum
                try:
                    edge_type = EdgeType(rel_type_str)
                except ValueError:
                    # Fallback for unknown types or custom types not in enum
                    logger.debug(f"Skipping unknown edge type: {rel_type_str}")
                    continue

                # Infer target node type based on edge type
                target_type = self._infer_target_type(edge_type)
                
                # Create the edge
                self.service.create_link(
                    src_ref=(NodeType.MEMORY, memory_id),
                    dst_ref=(target_type, target_id),
                    rel=edge_type,
                    weight=weight
                )
                
            except Exception as e:
                logger.error(f"Failed to sync relation '{key}': {e}")

    def _infer_target_type(self, edge_type: EdgeType) -> NodeType:
        # Heuristics mapping
        if edge_type == EdgeType.CRYSTALLIZED_FROM:
            return NodeType.MEMORY # Usually STS
        if edge_type == EdgeType.MERGED_INTO:
            return NodeType.MEMORY
        if edge_type == EdgeType.PRODUCES_SKILL:
            return NodeType.SKILL
        if edge_type == EdgeType.USES_SKILL:
            return NodeType.SKILL
        return NodeType.MEMORY # Default
