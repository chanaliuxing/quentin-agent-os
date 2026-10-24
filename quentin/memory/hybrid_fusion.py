from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    id: str
    path: str
    content: str
    score: float = 0.0
    metadata: Dict[str, Any] = None

def rrf_merge(
    vector_results: List[SearchResult],
    keyword_results: List[SearchResult],
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
    k: int = 60
) -> List[SearchResult]:
    """
    P5: Ported from OpenClaw's 'mergeHybridResults' in hybrid.ts.
    Uses Reciprocal Rank Fusion to merge semantic and keyword results.
    """
    scores: Dict[str, float] = {}
    items: Dict[str, SearchResult] = {}

    # Helper to process a ranked list
    def process_list(results: List[SearchResult], weight: float):
        for rank, res in enumerate(results):
            # RRF Formula: weight * (1 / (k + rank))
            rrf_score = weight * (1.0 / (k + rank + 1))
            if res.id not in scores:
                scores[res.id] = 0.0
                items[res.id] = res
            scores[res.id] += rrf_score

    process_list(vector_results, vector_weight)
    process_list(keyword_results, keyword_weight)

    # Sort by the new fused score
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    final_results = []
    for sid in sorted_ids:
        item = items[sid]
        item.score = scores[sid]
        final_results.append(item)
        
    return final_results

def bm25_normalize(raw_rank: float) -> float:
    """
    P5: Ported from OpenClaw's 'bm25RankToScore'.
    Converts SQLite FTS5 rank (negative, unbounded) to a normalized score.
    """
    # SQLite FTS5 rank: lower is better (more negative).
    # OpenClaw uses a simple inverse mapping or rank-based normalization.
    if raw_rank >= 0: return 0.0
    return 1.0 / (1.0 + abs(raw_rank))
