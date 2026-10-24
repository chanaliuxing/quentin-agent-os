# quentin/memory/processors/dedup.py
from __future__ import annotations
from typing import Optional, List
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier, MemoryRecord

class Deduplicator:
    def __init__(self, fabric: MemoryFabric, threshold: float = 0.9):
        self.fabric = fabric
        self.threshold = threshold

    def find_duplicate(self, vector: List[float], tier: MemoryTier = MemoryTier.MTS) -> Optional[MemoryRecord]:
        """
        Search for existing records in the target tier that are semantically identical.
        """
        if not vector:
            return None
            
        # Recall from specific tier with vector
        results = self.fabric.recall(
            MemoryQuery(
                vector=vector,
                tier=tier,
                top_k=1,
                min_importance=0.0 
            )
        )
        
        if not results:
            return None
            
        best_match = results[0]
        
        # Double check similarity threshold
        if best_match.vector:
            sim = self._cosine_sim(vector, best_match.vector)
            if sim >= self.threshold:
                return best_match
                
        return None

    def _cosine_sim(self, v1: List[float], v2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        norm_a = sum(a * a for a in v1) ** 0.5
        norm_b = sum(b * b for b in v2) ** 0.5
        if norm_a == 0 or norm_b == 0: return 0.0
        return dot / (norm_a * norm_b)