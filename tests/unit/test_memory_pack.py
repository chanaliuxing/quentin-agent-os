from __future__ import annotations

import asyncio

from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.tools.packs.memory_pack import MemoryPack
from quentin.infra.concurrency.cancellation import CancellationToken
from quentin.tools.manager import ToolCallContext


class _FakeFabric:
    def __init__(self) -> None:
        self.records = [
            MemoryRecord.new(tier=MemoryTier.STS, content="hello", source="session_delta:s1"),
            MemoryRecord.new(tier=MemoryTier.MTS, content="world", source="session_delta:s2"),
        ]
        self.last_session_options = None

    def recall(self, query):  # noqa: ANN001
        _ = query
        return list(self.records[:1])

    def recall_across_sessions(self, **kwargs):  # noqa: ANN003
        self.last_session_options = kwargs.get("session_options")
        return {
            "records": list(self.records),
            "session_hits": {"s1": 1, "s2": 1},
            "errors": {},
            "timed_out_sessions": [],
        }

    async def recall_across_sessions_async(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        return {
            "records": list(self.records[:1]),
            "session_hits": {"s1": 1},
            "errors": {"s2": "timeout(0.1s)"},
            "timed_out_sessions": ["s2"],
            "cancelled_sessions": [],
            "cancelled": False,
        }


class _CancelAwareFabric(_FakeFabric):
    async def recall_across_sessions_async(self, **kwargs):  # noqa: ANN003
        cancel_event = kwargs.get("cancel_event")
        cancelled = bool(cancel_event is not None and cancel_event.is_set())
        return {
            "records": [],
            "session_hits": {},
            "errors": {"s1": "cancelled"} if cancelled else {},
            "timed_out_sessions": [],
            "cancelled_sessions": ["s1"] if cancelled else [],
            "cancelled": cancelled,
        }


def test_memory_pack_single_recall() -> None:
    pack = MemoryPack(memory_fabric=_FakeFabric())
    _, handler = pack.get_tools()[0]
    res = asyncio.run(handler({"query": "hello", "mode": "text_only", "top_k": 3}))
    assert res["status"] == "ok"
    assert res["kind"] == "single"
    assert res["count"] == 1


def test_memory_pack_cross_session_sync_recall() -> None:
    fabric = _FakeFabric()
    pack = MemoryPack(memory_fabric=fabric)
    _, handler = pack.get_tools()[0]
    res = asyncio.run(
        handler(
            {
                "query": "h",
                "session_sources": {"s1": ["session_delta:s1"], "s2": ["session_delta:s2"]},
                "session_options": {"s1": {"priority": 3, "weight": 2.0}},
                "top_k": 5,
            }
        )
    )
    assert res["status"] == "ok"
    assert res["kind"] == "cross_session"
    assert res["count"] == 2
    assert res["session_hits"]["s1"] == 1
    assert isinstance(fabric.last_session_options, dict)
    assert fabric.last_session_options["s1"]["priority"] == 3


def test_memory_pack_cross_session_async_recall() -> None:
    pack = MemoryPack(memory_fabric=_FakeFabric())
    _, handler = pack.get_tools()[0]
    res = asyncio.run(
        handler(
            {
                "query": "h",
                "session_sources": {"s1": ["session_delta:s1"], "s2": ["session_delta:s2"]},
                "async_search": True,
                "overall_timeout_s": 1.0,
            }
        )
    )
    assert res["status"] == "ok"
    assert res["kind"] == "cross_session"
    assert res["count"] == 1
    assert "s2" in res["timed_out_sessions"]


def test_memory_pack_passes_cancel_token_to_async_search() -> None:
    pack = MemoryPack(memory_fabric=_CancelAwareFabric())
    _, handler = pack.get_tools()[0]
    token = CancellationToken()
    token.cancel("user")
    ctx = ToolCallContext(cancel_token=token)
    res = asyncio.run(
        handler(
            {
                "query": "h",
                "session_sources": {"s1": ["session_delta:s1"]},
                "async_search": True,
            },
            ctx=ctx,
        )
    )
    assert res["status"] == "ok"
    assert res["cancelled"] is True
    assert "s1" in res["cancelled_sessions"]
