from __future__ import annotations

import math
from typing import List, Dict, Any, Tuple

class HybridScorer:
    """
    Implements OpenClaw's hybrid score normalization logic.
    Formula: score = (vector_weight * cosine_sim) + (keyword_weight * (1 / (1 + bm25_rank)))
    """
    
    @staticmethod
    def normalize_keyword_rank(rank: int) -> float:
        """
        Converts a discrete rank (1st, 2nd, etc.) into a 0-1 normalized score.
        1st -> 0.5
        2nd -> 0.33
        """
        return 1.0 / (1.0 + float(rank))

    @classmethod
    def fuse_results(
        cls, 
        vector_results: List[Tuple[str, float]],  # (id, score)
        keyword_results: List[str],               # [id1, id2, ...] in order of rank
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> List[Tuple[str, float]]:
        
        combined_scores: Dict[str, float] = {}
        
        # 1. Process Vector Scores
        for res_id, score in vector_results:
            combined_scores[res_id] = combined_scores.get(res_id, 0.0) + (score * vector_weight)
            
        # 2. Process Keyword Ranks
        for rank, res_id in enumerate(keyword_results, start=1):
            normalized = cls.normalize_keyword_rank(rank)
            combined_scores[res_id] = combined_scores.get(res_id, 0.0) + (normalized * keyword_weight)
            
        # 3. Sort by combined score
        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results

# Global instance
hybrid_scorer = HybridScorer()
