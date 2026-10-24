from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
from quentin.utils.time import now_utc, now_iso
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)
from quentin.runtime.session_write_lock import acquire_session_write_lock


class TraceEventType(str, Enum):
    TASK_RECEIVED = "task_received"
    PLANNING = "planning"
    EXECUTION = "execution"
    TOOL_CALL = "tool_call"
    MODEL_CALL = "model_call"
    DECISION = "decision"
    CRITIC = "critic"
    IMMUNE = "immune"
    SLEEP = "sleep"
    MEMORY = "memory"
    SKILL_EVOLUTION = "skill_evolution"
    SELF_PROGRAMMING = "self_programming"
    SUMMARY = "summary"
    ERROR = "error"


@dataclass
class TraceEvent:
    event_id: str
    trace_id: str
    event_type: str
    timestamp: str = field(default_factory=now_iso)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        from quentin.utils.json import make_jsonable
        return make_jsonable(self)


@dataclass
class ExecutionSummary:
    """
    一次任务完成后的结构化总结。
    """
    trace_id: str
    task_id: str
    status: str  # "success" | "failed" | "partial"
    result_preview: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        from quentin.utils.json import make_jsonable
        return make_jsonable(self)


@dataclass
class LessonsLearned:
    """
    Critic / Sleep Loop 生成的“经验教训”，可以写入 Memory Fabric。
    """
    trace_id: str
    task_id: str
    content: str
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        from quentin.utils.json import make_jsonable
        return make_jsonable(self)


class TraceRecorder:
    """
    Trace 记录接口：所有 loop 都只依赖这个接口，不依赖具体存储。
    """

    def record_event(self, event: TraceEvent) -> None:  # pragma: no cover - interface
        raise RuntimeError("TraceRecorder is an interface; use JsonlTraceRecorder (or a concrete recorder).")

    def record_summary(self, summary: ExecutionSummary) -> None:  # pragma: no cover
        raise RuntimeError("TraceRecorder is an interface; use JsonlTraceRecorder (or a concrete recorder).")

    def record_lessons(self, lessons: LessonsLearned) -> None:  # pragma: no cover
        raise RuntimeError("TraceRecorder is an interface; use JsonlTraceRecorder (or a concrete recorder).")


class JsonlTraceRecorder(TraceRecorder):
    """
    非常简单的 JSONL Trace 记录器：
      - data/traces/events.jsonl
      - data/traces/summaries.jsonl
      - data/traces/lessons.jsonl

    后面可以由自迭代去升级成 ClickHouse / DuckDB / 向量库等。
    """

    def __init__(self, repo_root: str | None = None) -> None:
        import json
        self._json = json
        from quentin.traces.paths import resolve_traces_dir

        root = Path(repo_root or ".").resolve()
        traces_dir = resolve_traces_dir(repo_root=root)
        traces_dir.mkdir(parents=True, exist_ok=True)

        self._events_path = traces_dir / "events.jsonl"
        self._summaries_path = traces_dir / "summaries.jsonl"
        self._lessons_path = traces_dir / "lessons.jsonl"

    def _append_line(self, path: Path, obj: Dict[str, Any]) -> None:
        # P5: Surgery Fifty-five - Trace Compression and Blob Offloading (OpenClaw Parity)
        gz_path = Path(str(path) + ".gz")
        gz_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Offload large payloads to BlobStore
        from quentin.infra.storage.blob_store import blob_store
        if "payload" in obj:
            obj["payload"] = blob_store.offload_if_large(obj["payload"])
        
        lock = acquire_session_write_lock(session_file=gz_path)
        try:
            import gzip
            def default_handler(o):
                if hasattr(o, "__dict__"):
                    return f"<{o.__class__.__name__}>"
                return str(o)

            # Atomic Gzip Append
            line = self._json.dumps(obj, ensure_ascii=False, default=default_handler) + "\n"
            with gzip.open(gz_path, "at", encoding="utf-8") as f:
                f.write(line)
        finally:
            lock["release"]()

    def record_event(self, *args, **kwargs) -> None:
        event: Optional[TraceEvent] = None
        if args and isinstance(args[0], TraceEvent):
            event = args[0]
        elif "event" in kwargs and isinstance(kwargs["event"], TraceEvent):
            event = kwargs["event"]
        elif "event_type" in kwargs and "trace_id" in kwargs:
            # Reconstruct TraceEvent from kwargs if it looks like a direct call
            event_type_val = kwargs.get("event_type")
            if isinstance(event_type_val, str):
                try:
                    event_type_val = TraceEventType(event_type_val)
                except ValueError:
                    logger.warning(f"Invalid event_type string: {event_type_val}. Using raw string.")
            
            event = TraceEvent(
                event_id=str(uuid.uuid4()),
                trace_id=kwargs.get("trace_id"), # type: ignore
                event_type=event_type_val.value if isinstance(event_type_val, TraceEventType) else str(event_type_val), # type: ignore
                timestamp=now_utc().isoformat(),
                payload=kwargs.get("payload", {}),
            )
        
        if event:
            self._append_line(self._events_path, event.to_dict())
        else:
            logger.warning(f"JsonlTraceRecorder.record_event called with unparseable arguments: args={args}, kwargs={kwargs}")

    def record_summary(self, summary: ExecutionSummary) -> None:
        self._append_line(self._summaries_path, summary.to_dict())

    def record_lessons(self, lessons: LessonsLearned) -> None:
        self._append_line(self._lessons_path, lessons.to_dict())


def new_trace_event(
    trace_id: str,
    event_type: TraceEventType,
    payload: Optional[Dict[str, Any]] = None,
) -> TraceEvent:
    return TraceEvent(
        event_id=str(uuid.uuid4()),
        trace_id=trace_id,
        event_type=event_type.value,
        timestamp=now_utc().isoformat(),
        payload=payload or {},
    )
