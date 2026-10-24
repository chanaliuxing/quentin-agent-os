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


def _add_record(
    fabric: MemoryFabric,
    *,
    content: str,
    kind: str,
    vector: list[float],
) -> MemoryRecord:
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content=content,
        source="test",
        kind=kind,
        importance=0.7,
        vector=vector,
    )
    fabric.store.add(rec)
    return rec


@pytest.mark.parametrize("kind", KINDS)
def test_vector_only_recall_preserves_new_memory_kinds(kind: str) -> None:
    fabric = MemoryFabric(db_path=":memory:")
    target = _add_record(
        fabric,
        content=f"{kind} target content",
        kind=kind,
        vector=[1.0, 0.0],
    )
    _add_record(
        fabric,
        content="other kind distractor",
        kind="episodic",
        vector=[0.0, 1.0],
    )

    results = fabric.recall(
        MemoryQuery(
            vector=[0.95, 0.05],
            mode="vector_only",
            kind=kind,
            top_k=5,
        )
    )

    assert results
    assert results[0].id == target.id
    assert all(r.kind == kind for r in results)


@pytest.mark.parametrize("kind", KINDS)
def test_hybrid_recall_respects_kind_filter_for_new_memory_kinds(kind: str) -> None:
    fabric = MemoryFabric(db_path=":memory:")
    target = _add_record(
        fabric,
        content=f"shared-token {kind} preferred",
        kind=kind,
        vector=[1.0, 0.0],
    )
    wrong_kind_text_match = _add_record(
        fabric,
        content="shared-token wrong-kind exact-text",
        kind="episodic",
        vector=[0.0, 1.0],
    )

    results = fabric.recall(
        MemoryQuery(
            text="shared-token",
            vector=[0.95, 0.05],
            mode="hybrid",
            kind=kind,
            top_k=5,
            k_text=5,
            k_vec=5,
            alpha=0.5,
        )
    )

    ids = [r.id for r in results]
    assert target.id in ids
    assert wrong_kind_text_match.id not in ids
    assert all(r.kind == kind for r in results)
