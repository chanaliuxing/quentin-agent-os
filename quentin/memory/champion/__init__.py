"""
Champion memory stack (B + C + D):
- B: dual-engine retrieval (dense vectors + sparse text/metadata)
- C: tiering hooks (hot/warm/cold) via payload filters / policies
- D: sparse retrieval + rerank hooks (FTS + alignment rerank in fabric)

This package is intentionally dependency-light (requests-based Qdrant REST).
"""

