import uuid
import asyncio
from typing import Any, Dict
from datetime import datetime
from quentin.utils.time import now_utc
from quentin.infra.storage.kv_store import KVStore
from quentin.traces.schemas import TraceSpan # Updated import
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event


class Tracer:
    """
    非常关键：所有 L0-L3 的行动都写 Trace。
    """

    def __init__(self, store: KVStore | None = None, *, repo_root: str = "."):
        self.store = store
        # Mirror spans to the JSONL trace stream for unified observability tooling.
        self._jsonl = JsonlTraceRecorder(repo_root=repo_root)

    async def _persist(self, span: TraceSpan) -> None:
        if not self.store:
            return
        
        # Conform to EpisodeProvider convention
        # 1. Save span detail
        await self.store.save(f"trace:span:{span.span_id}", span.model_dump())
        # 2. Append to index
        await self.store.append_list("trace:index:spans", span.span_id)
        
        # Also keep the old log list for backward compatibility/debug
        await self.store.append_list("trace_log", span.model_dump())

    def span(
        self,
        layer: str,
        event: str,
        module: str = "",
        input: Any | None = None,
        output: Any | None = None,
        meta: Dict[str, Any] | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            span_id=str(uuid.uuid4()),
            ts=now_utc(), # Changed timestamp to ts to match schema
            layer=layer,
            module=module,
            event=event,
            input=input or {},
            output=output or {},
            meta=meta or {},
        )
        
        # Fire and forget persist task
        if self.store:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._persist(span))
            except RuntimeError:
                # No running loop (e.g. unit tests or script start), skip persist or print warning
                pass

        # 你也可以同步输出到 stdout / json log
        print(f"[TRACE] {span.ts} {layer} {event} {span.meta}")
        # Best-effort: also emit to JSONL traces so blueprint tooling can detect execution.
        try:
            self._jsonl.record_event(
                new_trace_event(
                    trace_id=span.span_id,
                    event_type=TraceEventType.EXECUTION,
                    payload={
                        "action": "trace_span",
                        "layer": layer,
                        "event": event,
                        "module": module,
                        "meta": span.meta,
                    },
                )
            )
        except Exception:
            pass
        return span
