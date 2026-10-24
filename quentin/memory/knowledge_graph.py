from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class NodeType(str, Enum):
    MEMORY = "memory"
    ENTITY = "entity"
    CONCEPT = "concept"
    FILE = "file"

class EdgeType(str, Enum):
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    IMPLEMENTS = "implements"
    REFERENCES = "references"

@dataclass
class Triple:
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SimpleKnowledgeGraph:
    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root or ".").resolve()
        self.storage_path = self.repo_root / "data" / "knowledge" / "triples.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def add_triple(self, subj: str, pred: str, obj: str, source: str = "system") -> None:
        t = Triple(subject=str(subj), predicate=str(pred), object=str(obj), source=str(source))
        try:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"KG Error: {e}")

    def query(self, entity: str) -> List[Triple]:
        results = []
        if not self.storage_path.exists(): return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        if d["subject"] == entity or d["object"] == entity:
                            results.append(Triple(**d))
                    except: continue
        except: pass
        return results

    def get_context_text(self, entities: List[str]) -> str:
        facts = []
        for ent in entities:
            for t in self.query(ent):
                facts.append(f"- {t.subject} {t.predicate} {t.object}")
        if not facts: return ""
        return "\nRELEVANT KNOWLEDGE:\n" + "\n".join(list(set(facts))[:20]) + "\n"

class GraphService:
    """
    P5: Ported from OpenClaw's Graph Service.
    Provides standard node/edge synchronization.
    """
    def __init__(self):
        # We reuse the SimpleKnowledgeGraph for storage in this surgery
        from quentin.memory.knowledge_graph import SimpleKnowledgeGraph
        self.kg = SimpleKnowledgeGraph(".")

    def sync_node(self, node_type: NodeType, ref_id: str, title: str = ""):
        """Physical synchronization of a node."""
        logger.info(f"GraphService: Syncing {node_type} node: {ref_id} ({title[:30]})")
        # In a real system, upsert to a vector graph or DB.
        pass

    def sync_memory_relations(self, memory_id: str, relations: Dict[str, float], preview: str = ""):
        """Persists relations between a memory record and entities."""
        for ent, weight in relations.items():
            self.kg.add_triple(memory_id, EdgeType.RELATED_TO, ent)
