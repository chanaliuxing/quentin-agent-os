import asyncio

import pytest

from quentin.infra.concurrency.lanes import enqueue


@pytest.mark.asyncio
async def test_enqueue_serializes_same_session_lane() -> None:
    order: list[int] = []

    async def _work(i: int) -> int:
        order.append(i)
        await asyncio.sleep(0.01)
        return i

    a = enqueue("session:test", lambda: _work(1))
    b = enqueue("session:test", lambda: _work(2))
    res = await asyncio.gather(a, b)

    assert res == [1, 2]
    assert order == [1, 2]

