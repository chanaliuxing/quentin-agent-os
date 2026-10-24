from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import uuid

from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """
    Minimal structured trace record used by Immune/Sleep/BlueprintGapTracker.
    """

    trace_id: str
    task_id: str
    component_id: str

    blueprint_capability_id: Optional[str] = None
    target_module: Optional[str] = None
    target_symbol: Optional[str] = None

    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    start_time: str = field(default_factory=now_iso)
    end_time: str = field(default_factory=now_iso)

    metrics: Dict[str, float] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImmuneCase:
    case_id: str
    component_id: str
    severity: str
    action_type: str
    summary: str
    reason: str

    related_traces: List[str] = field(default_factory=list)
    blueprint_capability_id: Optional[str] = None
    proposed_module: Optional[str] = None
    proposed_symbol: Optional[str] = None

    created_at: str = field(default_factory=now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


TraceEvent = ExecutionTrace


class ExecutionTraceStore:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        store_path: str | Path = "data/traces.jsonl",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store_path = self.repo_root / store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, trace: ExecutionTrace) -> None:
        try:
            lock = acquire_session_write_lock(session_file=self.store_path)
            try:
                with self.store_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("ExecutionTraceStore.append failed")

    def iter_traces(self, limit: Optional[int] = None) -> List[ExecutionTrace]:
        traces: List[ExecutionTrace] = []
        if not self.store_path.exists():
            return traces

        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        traces.append(ExecutionTrace(**d))
                        if limit is not None and len(traces) >= limit:
                            break
                    except: pass
        except Exception:
            logger.exception("ExecutionTraceStore.iter_traces failed")

        return traces


FileBackedTraceStore = ExecutionTraceStore