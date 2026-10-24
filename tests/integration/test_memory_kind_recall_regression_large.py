from __future__ import annotations

import random

import pytest

from quentin.memory.fabric import MemoryFabric
from quentin.memory.kinds import (
    KIND_EXPECTED_STATE_TEMPLATE,
    KIND_GIST_MEMORY,
    KIND_SITUATION_PROFILE,
    KIND_TOOL_KNOWLEDGE,
)
from quentin.memory.models import MemoryQuery, MemoryRecord, MemoryTier


KINDS = [
    KIND_GIST_MEMORY,
    KIND_TOOL_KNOWLEDGE,
    KIND_SITUATION_PROFILE,
    KIND_EXPECTED_STATE_TEMPLATE,
]


def _vec(i: int, dim: int = 8) -> list[float]:
    rng = random.Random(20260328 + i)
    raw = [rng.random() for _ in range(dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


@pytest.mark.parametrize("kind", KINDS)
def test_large_sample_recall_quality_for_new_memory_kinds(kind: str) -> None:
    fabric = MemoryFabric(db_path=":memory:")
    n = 120
    target_ids: list[str] = []

    for i in range(n):
        token = f"[{kind}:{i:03d}]"
        rec = MemoryRecord.new(
            tier=MemoryTier.STS,
            content=f"{token} structured memory payload",
            source="regression",
            kind=kind,
            vector=_vec(i),
            importance=0.7,
        )
        fabric.store.add(rec)
        target_ids.append(rec.id)

        # Distractor different kind, similar shape.
        d = MemoryRecord.new(
            tier=MemoryTier.STS,
            content=f"[episodic:{i:03d}] distractor payload",
            source="regression",
            kind="episodic",
            vector=_vec(i + 10_000),
            importance=0.5,
        )
        fabric.store.add(d)

    hits = 0
    for i in range(0, n, 10):
        out = fabric.recall(MemoryQuery(vector=_vec(i), mode="vector_only", kind=kind, top_k=5))
        ids = {r.id for r in out}
        if target_ids[i] in ids:
            hits += 1
        assert all(r.kind == kind for r in out)

    hit_rate = hits / (n // 10)
    assert hit_rate >= 0.9
