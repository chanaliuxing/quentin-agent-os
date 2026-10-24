from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from .models import MemoryRecord, MemoryQuery, MemoryTier


class MemoryStore(ABC):
    @abstractmethod
    def init(self) -> None:
        ...

    @abstractmethod
    def add(self, record: MemoryRecord) -> None:
        ...

    # Optional bulk insert for high-throughput ingestion (benchmarks, sync).
    # Default implementation preserves behavior by delegating to add().
    def add_many(self, records: List[MemoryRecord]) -> None:
        for r in records or []:
            self.add(r)

    @abstractmethod
    def get(self, record_id: str) -> Optional[MemoryRecord]:
        ...

    @abstractmethod
    def update(self, record: MemoryRecord) -> None:
        ...

    @abstractmethod
    def search(self, query: MemoryQuery) -> List[MemoryRecord]:
        ...

    @abstractmethod
    def promote(self, record_id: str, to_tier: MemoryTier) -> None:
        ...

    @abstractmethod
    def mark_decayed(self, record_id: str) -> None:
        ...

    @abstractmethod
    def get_candidates_for_consolidation(
        self,
        tier: MemoryTier,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        ...

    # Optional fast-path for recall access bookkeeping.
    # Stores that don't override can keep existing update(record) behavior.
    def touch_access_many(self, record_ids: List[str], at: datetime) -> None:
        return None
