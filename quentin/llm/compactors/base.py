from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class CompactionResult:
    text: str
    original_chars: int
    compacted_chars: int
    method: str

class BaseCompactor(ABC):
    @abstractmethod
    def compact(self, text: str, target_chars: int) -> CompactionResult:
        pass
