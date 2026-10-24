from __future__ import annotations
from enum import Enum
import re

class QueryIntent(str, Enum):
    KEYWORD_EXACT = "keyword_exact"
    SEMANTIC_EXPLORE = "semantic_explore"
    MIXED = "mixed"

class IntentRouter:
    """
    Routes memory queries based on structure.
    """
    def route(self, query: str) -> QueryIntent:
        # Heuristic v1
        if '"' in query or "'" in query:
            return QueryIntent.KEYWORD_EXACT
        if len(query.split()) > 5:
            return QueryIntent.SEMANTIC_EXPLORE
        return QueryIntent.MIXED

intent_router = IntentRouter()
