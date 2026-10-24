from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from quentin.runtime.session_write_lock import acquire_session_write_lock


def _now() -> float:
    return time.time()


def _hash_bucket(key: str) -> float:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    # 0..1 bucket
    return int(h[:8], 16) / float(0xFFFFFFFF)


@dataclass
class OnlineABDecision:
    experiment_id: str
    routing_key: str
    variant_id: str
    fraction: float
    created_at: float = field(default_factory=_now)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OnlineABMetric:
    experiment_id: str
    routing_key: str
    variant_id: str
    success: Optional[bool] = None
    latency_ms: Optional[float] = None
    cost_tokens: Optional[float] = None
    created_at: float = field(default_factory=_now)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OnlineABStore:
    def __init__(
        self,
        *,
        decisions_path: str | Path = "data/research/online_ab_decisions.jsonl",
        metrics_path: str | Path = "data/research/online_ab_metrics.jsonl",
    ) -> None:
        self.decisions_path = Path(decisions_path)
        self.metrics_path = Path(metrics_path)
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

    def append_decision(self, d: OnlineABDecision) -> None:
        lock = acquire_session_write_lock(session_file=self.decisions_path)
        try:
            with self.decisions_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

    def append_metric(self, m: OnlineABMetric) -> None:
        lock = acquire_session_write_lock(session_file=self.metrics_path)
        try:
            with self.metrics_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()


def choose_variant(
    *,
    routing_key: str,
    baseline_variant_id: str,
    candidate_variant_id: str,
    fraction: float,
) -> str:
    """
    Minimal online A/B routing:
    - fraction in [0,1] routes that fraction to candidate, otherwise baseline.
    """
    frac = max(0.0, min(1.0, float(fraction)))
    b = _hash_bucket(routing_key)
    return candidate_variant_id if b < frac else baseline_variant_id

