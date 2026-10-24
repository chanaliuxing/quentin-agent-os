from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import List

from quentin.memory.models import MemoryRecord


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9_]+", (text or "").lower()) if t]


@dataclass(frozen=True)
class RerankResult:
    record: MemoryRecord
    score: float


class ChampionReranker:
    def rerank(self, *, query_text: str, records: List[MemoryRecord], top_k: int) -> List[MemoryRecord]:
        return records[:top_k]


class LexicalReranker(ChampionReranker):
    """
    Dependency-free reranker.
    Blend of exact phrase + token overlap + rank prior.
    """

    def rerank(self, *, query_text: str, records: List[MemoryRecord], top_k: int) -> List[MemoryRecord]:
        q = (query_text or "").strip().lower()
        if not q:
            return records[:top_k]
        q_tokens = _tokenize(q)
        if not q_tokens:
            return records[:top_k]

        scored: List[RerankResult] = []
        for idx, rec in enumerate(records):
            content = str(getattr(rec, "content", "") or "").lower()
            if not content:
                scored.append(RerankResult(record=rec, score=-idx * 1e-3))
                continue
            exact = 1.0 if q in content else 0.0
            overlap = sum(1 for t in q_tokens if t in content) / float(len(q_tokens))
            prior = float(getattr(rec, "importance", 0.0) or 0.0)
            score = (2.0 * exact) + (1.2 * overlap) + (0.1 * prior) - (idx * 1e-3)
            scored.append(RerankResult(record=rec, score=score))

        scored.sort(key=lambda x: x.score, reverse=True)
        out = [x.record for x in scored[:top_k]]
        for i, rec in enumerate(out):
            rec.importance = max(float(getattr(rec, "importance", 0.0) or 0.0), 1.0 - (i / max(1, top_k)))
        return out


class CrossEncoderReranker(ChampionReranker):
    """
    Optional heavy reranker. Requires sentence-transformers / torch.
    Uses a small cross-encoder when available.
    """

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder  # type: ignore

        model_name = (os.getenv("QUENTIN_CHAMPION_RERANK_MODEL") or "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()
        self._model = CrossEncoder(model_name)

    def rerank(self, *, query_text: str, records: List[MemoryRecord], top_k: int) -> List[MemoryRecord]:
        q = (query_text or "").strip()
        if not q or not records:
            return records[:top_k]
        pairs = [(q, str(getattr(r, "content", "") or "")) for r in records]
        scores = list(self._model.predict(pairs))
        scored = list(zip(scores, records))
        scored.sort(key=lambda x: float(x[0]), reverse=True)
        out = [r for _, r in scored[:top_k]]
        # squash score into [0,1] importance hint
        for s, rec in scored[:top_k]:
            try:
                rec.importance = max(float(getattr(rec, "importance", 0.0) or 0.0), 1.0 / (1.0 + math.exp(-float(s))))
            except Exception:
                pass
        return out


def build_reranker() -> ChampionReranker | None:
    mode = (os.getenv("QUENTIN_CHAMPION_RERANKER") or "off").strip().lower()
    if mode in ("", "0", "off", "none"):
        return None
    if mode in ("lexical", "light"):
        return LexicalReranker()
    if mode in ("cross_encoder", "ce"):
        try:
            return CrossEncoderReranker()
        except Exception:
            # graceful fallback in restricted/offline envs
            return LexicalReranker()
    return LexicalReranker()

