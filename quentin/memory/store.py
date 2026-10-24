# quentin/memory/store.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from quentin.memory.schemas import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


class FileBackedMemoryStore:
    """
    最简单版的 Memory 存储：一个 JSON 文件 {memory_id: MemoryEntryDict}
    将来可以替换成 SQLite / 向量库，但对上层 API 不变。
    """

    def __init__(self, path: str | Path = "data/memory.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.exception("Failed to load memory from %s", self.path)
                self._cache = {}
        else:
            self._cache = {}
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    # ---------- CRUD ----------

    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        self._load()
        d = self._cache.get(memory_id)
        return MemoryEntry.from_dict(d) if d else None

    def upsert(self, entry: MemoryEntry) -> None:
        self._load()
        self._cache[entry.memory_id] = entry.to_dict()
        self._save()

    def delete(self, memory_id: str) -> None:
        self._load()
        if memory_id in self._cache:
            del self._cache[memory_id]
            self._save()

    def all_entries(self) -> List[MemoryEntry]:
        self._load()
        return [MemoryEntry.from_dict(d) for d in self._cache.values()]

    def list_by_tier(self, tier: MemoryTier) -> List[MemoryEntry]:
        return [e for e in self.all_entries() if e.memory_tier == tier]

    def count_by_tier(self) -> Dict[str, int]:
        counts: Dict[str, int] = {"STS": 0, "MTS": 0, "LTS": 0}
        for e in self.all_entries():
            if e.memory_tier in counts:
                counts[e.memory_tier] += 1
        return counts
