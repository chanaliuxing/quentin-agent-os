# quentin/knowledge_graph/schema.py
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class NodeType(str, Enum):
    MEMORY = "memory"       # STS/MTS/LTS record
    TRACE = "trace"         # Execution trace
    SKILL = "skill"         # Registered skill
    CANDIDATE = "candidate" # Skill candidate
    GOAL = "goal"           # GoalSpec
    PATCH = "patch"         # Code patch
    CONCEPT = "concept"     # Extracted semantic concept

class EdgeType(str, Enum):
    CRYSTALLIZED_FROM = "crystallized_from" # MTS -> STS (SleepLoop)
    SUMMARIZED_BY = "summarized_by"         # STS -> MTS (Inverse)
    MERGED_INTO = "merged_into"             # Old MTS -> New MTS
    SIMILAR_TO = "similar_to"               # Vector similarity
    SUPPORTS = "supports"                   # Evidence -> Conclusion
    PRODUCES_SKILL = "produces_skill"       # Trace/Candidate -> Skill
    USES_SKILL = "uses_skill"               # Trace -> Skill
    ADDRESSES = "addresses"                 # Patch -> Issue/Gap
    RELATED_TO = "related_to"               # General relationship
    DEPENDS_ON = "depends_on"               # Dependency
    IMPLEMENTS = "implements"               # Implementation
    PART_OF = "part_of"                     # Composition

@dataclass
class KGNode:
    node_id: str
    node_type: NodeType
    ref_id: str             # ID in the source table (e.g., memory_id)
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

@dataclass
class KGEdge:
    edge_id: str
    src_node_id: str
    dst_node_id: str
    edge_type: EdgeType
    weight: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict) # e.g. { "confidence": 0.9 }
    created_at: Optional[datetime] = None

    @staticmethod
    def new(src: str, dst: str, rel: EdgeType, weight: float = 1.0, evidence: dict = None) -> 'KGEdge':
        return KGEdge(
            edge_id=str(uuid.uuid4()),
            src_node_id=src,
            dst_node_id=dst,
            edge_type=rel,
            weight=weight,
            evidence=evidence or {}
        )