from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Tuple
from quentin.tools.packs.base import ToolPack
from quentin.tools.schemas import ToolSpec
from quentin.memory.models import MemoryQuery, MemoryRecord

class MemoryPack(ToolPack):
    def __init__(self, memory_fabric: Any = None):
        self._memory_fabric = memory_fabric

    @property
    def domain(self) -> str:
        return "memory"

    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        recall_spec = ToolSpec(
            name="memory.recall",
            description="Recall relevant past experiences, code snippets, or decisions from the long-term memory fabric.",
            domain="memory",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": ["auto", "text_only", "vector_only", "hybrid"]},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 200},
                    "tier": {"type": "string", "enum": ["STS", "MTS", "LTS"]},
                    "session_sources": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "session_options": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "weight": {"type": "number"},
                                "priority": {"type": "integer"},
                                "top_k_override": {"type": "integer"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "async_search": {"type": "boolean"},
                    "overall_timeout_s": {"type": "number", "minimum": 0.1},
                },
                "additionalProperties": True,
            },
        )

        def _record_to_dict(rec: MemoryRecord) -> Dict[str, Any]:
            return {
                "id": rec.id,
                "tier": getattr(rec.tier, "value", str(rec.tier)),
                "source": rec.source,
                "importance": float(rec.importance or 0.0),
                "content": rec.content,
                "metadata": dict(rec.metadata or {}),
            }

        async def memory_recall_handler(params: dict, ctx: Any = None):
            _ = ctx
            if self._memory_fabric is None:
                return {"status": "error", "error": "memory_fabric_unavailable"}

            text = str(params.get("query") or params.get("text") or "").strip()
            mode = str(params.get("mode") or "auto").strip().lower()
            try:
                top_k = max(1, min(200, int(params.get("top_k", 10))))
            except Exception:
                top_k = 10

            query = MemoryQuery(text=text or None, mode=mode or "auto", top_k=top_k)
            tier_raw = str(params.get("tier") or "").strip()
            if tier_raw:
                try:
                    from quentin.memory.models import MemoryTier

                    query.tier = MemoryTier.from_str(tier_raw)
                except Exception:
                    pass

            session_sources = params.get("session_sources")
            session_options = params.get("session_options")
            if isinstance(session_sources, dict) and session_sources:
                async_search = bool(params.get("async_search"))
                if async_search and hasattr(self._memory_fabric, "recall_across_sessions_async"):
                    overall_timeout_s = params.get("overall_timeout_s")
                    try:
                        timeout_val = float(overall_timeout_s) if overall_timeout_s is not None else None
                    except Exception:
                        timeout_val = None
                    cancel_event = None
                    watcher_task = None
                    if getattr(ctx, "cancel_token", None) is not None:
                        cancel_event = asyncio.Event()
                        if ctx.cancel_token.is_cancelled():
                            cancel_event.set()
                        else:
                            async def _watch_cancel() -> None:
                                while True:
                                    if ctx.cancel_token.is_cancelled():
                                        cancel_event.set()
                                        return
                                    await asyncio.sleep(0.05)
                            watcher_task = asyncio.create_task(_watch_cancel())
                    result = await self._memory_fabric.recall_across_sessions_async(
                        query=query,
                        session_sources=session_sources,
                        session_options=session_options if isinstance(session_options, dict) else None,
                        cancel_event=cancel_event,
                        overall_timeout_s=timeout_val,
                    )
                    if watcher_task is not None:
                        watcher_task.cancel()
                else:
                    result = self._memory_fabric.recall_across_sessions(
                        query=query,
                        session_sources=session_sources,
                        session_options=session_options if isinstance(session_options, dict) else None,
                    )
                records = result.get("records") or []
                return {
                    "status": "ok",
                    "kind": "cross_session",
                    "count": len(records),
                    "records": [_record_to_dict(r) for r in records],
                    "session_hits": result.get("session_hits") or {},
                    "errors": result.get("errors") or {},
                    "timed_out_sessions": result.get("timed_out_sessions") or [],
                    "cancelled_sessions": result.get("cancelled_sessions") or [],
                    "cancelled": bool(result.get("cancelled")),
                }

            records = self._memory_fabric.recall(query)
            return {
                "status": "ok",
                "kind": "single",
                "count": len(records),
                "records": [_record_to_dict(r) for r in records],
            }

        return [
            (recall_spec, memory_recall_handler)
        ]
