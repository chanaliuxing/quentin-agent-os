from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
import json
import time

from quentin.runtime.session_write_lock import acquire_session_write_lock


@dataclass
class RouterStat:
    mode: str
    task_type: str
    model: str
    provider: str
    latency_ms: float
    success: bool
    score: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def append_router_stat(
    *,
    repo_root: str | Path = ".",
    path: str | Path = "data/model_router_stats.jsonl",
    record: RouterStat,
) -> None:
    root = Path(repo_root).resolve()
    out = root / path
    out.parent.mkdir(parents=True, exist_ok=True)
    if record.timestamp <= 0:
        record.timestamp = time.time()
    lock = acquire_session_write_lock(session_file=out)
    try:
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    finally:
        lock["release"]()

