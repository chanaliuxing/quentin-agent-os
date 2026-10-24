# quentin/memory/processors/cluster.py
from __future__ import annotations
import math
from typing import List
from dataclasses import dataclass
from quentin.memory.models import MemoryRecord

@dataclass
class Cluster:
    center_vector: List[float]
    records: List[MemoryRecord]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def cluster_records(
    records: List[MemoryRecord], 
    similarity_threshold: float = 0.85
) -> List[Cluster]:
    """
    Greedy clustering implementation:
    1. Pick the first record as a seed.
    2. Find all other records similar to it (>= threshold).
    3. Form a cluster.
    4. Repeat for remaining records.
    """
    # Filter out records without vectors (Phase 1 dependency)
    valid_records = [r for r in records if r.vector and len(r.vector) > 0]
    
    clusters: List[Cluster] = []
    pool = valid_records[:]
    
    while pool:
        seed = pool.pop(0)
        seed_vec = seed.vector
        current_cluster_records = [seed]
        
        next_pool = []
        for candidate in pool:
            # We know vector is not None due to filter above
            sim = cosine_similarity(seed_vec, candidate.vector) # type: ignore
            if sim >= similarity_threshold:
                current_cluster_records.append(candidate)
            else:
                next_pool.append(candidate)
        
        pool = next_pool
        
        # Calculate cluster center (average vector)
        dim = len(seed_vec) # type: ignore
        center = [0.0] * dim
        count = len(current_cluster_records)
        
        for r in current_cluster_records:
            if r.vector:
                for i in range(dim):
                    center[i] += r.vector[i]
        
        center = [x / count for x in center]
        
        clusters.append(Cluster(center_vector=center, records=current_cluster_records))
        
    return clusters