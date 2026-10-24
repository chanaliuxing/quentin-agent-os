from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.memory.models import MemoryQuery


@dataclass
class MemoryRecallVariant:
    mode: Optional[str] = None
    alpha: Optional[float] = None
    k_text: Optional[int] = None
    k_vec: Optional[int] = None
    min_text_score: Optional[float] = None
    min_vec_score: Optional[float] = None
    text_mode: Optional[str] = None
    vec_backend: Optional[str] = None

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "MemoryRecallVariant":
        return cls(
            mode=params.get("mode"),
            alpha=params.get("alpha"),
            k_text=params.get("k_text"),
            k_vec=params.get("k_vec"),
            min_text_score=params.get("min_text_score"),
            min_vec_score=params.get("min_vec_score"),
            text_mode=params.get("text_mode"),
            vec_backend=params.get("vec_backend"),
        )

    def apply(self, base_query: MemoryQuery) -> MemoryQuery:
        payload = dict(base_query.__dict__)
        if self.mode is not None:
            payload["mode"] = self.mode
        if self.alpha is not None:
            payload["alpha"] = self.alpha
        if self.k_text is not None:
            payload["k_text"] = self.k_text
        if self.k_vec is not None:
            payload["k_vec"] = self.k_vec
        if self.min_text_score is not None:
            payload["min_text_score"] = self.min_text_score
        if self.min_vec_score is not None:
            payload["min_vec_score"] = self.min_vec_score
        if self.text_mode is not None:
            payload["text_mode"] = self.text_mode
        return MemoryQuery(**payload)
