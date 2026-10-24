from __future__ import annotations
from typing import Dict
from .base import BaseCompactor
from .truncate_compactor import TruncateCompactor
from .summary_compactor import SummaryCompactor

class CompactorRouter:
    def __init__(self):
        self._compactors: Dict[str, BaseCompactor] = {
            "truncate": TruncateCompactor(),
            "summary": SummaryCompactor(),
        }
        
    def get_compactor(self, name: str = "truncate") -> BaseCompactor:
        return self._compactors.get(name, self._compactors["truncate"])

# Global instance
compactor_router = CompactorRouter()
