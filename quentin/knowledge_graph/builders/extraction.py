# quentin/knowledge_graph/builders/extraction.py
from __future__ import annotations
import logging
import json
from typing import Dict, Any, List
from ..schema import NodeType, EdgeType
from ..service import GraphService

logger = logging.getLogger(__name__)

class GraphKnowledgeExtractor:
    """
    Uses LLM to extract entity-relations from text and stores them in GraphService.
    """
    def __init__(self, service: GraphService):
        self.service = service

    async def extract_and_store(self, text: str, context: Dict[str, Any] = None):
        """
        Extracts triples and syncs them to the industrial graph store.
        """
        from quentin.llm.client import call_llm
        
        prompt = (
            "Extract knowledge triples (entities and their relations) from the text below.\n"
            "Respond ONLY with a JSON list of objects with keys: source, relation, target.\n"
            "The 'relation' should map to one of these types if possible: "
            "depends_on, implements, uses, crystallized_from, part_of, related_to.\n"
            f"TEXT: {text[:3000]}"
        )
        
        try:
            model = os.getenv("LLM_MODEL")
            if not model:
                # We can fallback to 'ollama' provider with the env-based default if we want,
                # but better to use the centralized call_llm logic.
                from types import SimpleNamespace
                model = SimpleNamespace(name=os.getenv("LLM_MODEL"), provider="ollama")

            res = call_llm(
                config=os.getenv("LLM_MODEL"), 
                user_prompt=prompt, 
                actor="kg_extractor",
                system_prompt="You are a knowledge graph engineer. Extract meaningful relations."
            )
            
            # Robust JSON parsing
            import re
            match = re.search(r"\[.*\]", res, re.DOTALL)
            if not match:
                logger.warning("KG Extraction: No JSON array found in LLM response.")
                return
            
            triples = json.loads(match.group(0))
            count = 0
            for t in triples:
                source = str(t.get("source", "")).strip()
                target = str(t.get("target", "")).strip()
                rel_str = str(t.get("relation", "related_to")).strip().lower()
                
                if not source or not target:
                    continue
                
                # Map to EdgeType
                try:
                    rel = EdgeType(rel_str)
                except ValueError:
                    rel = EdgeType.RELATED_TO
                
                # Sync nodes and link
                # We assume generic CONCEPT type for extracted entities unless otherwise known
                self.service.create_link(
                    src_ref=(NodeType.CONCEPT, source),
                    dst_ref=(NodeType.CONCEPT, target),
                    rel=rel
                )
                count += 1
                
            logger.info(f"GraphKnowledgeExtractor: Extracted and stored {count} relations.")
            
        except Exception as e:
            logger.error(f"GraphKnowledgeExtractor: Extraction failed: {e}")
